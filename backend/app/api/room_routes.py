"""Room HTTP routes and the /ws/room socket. Rules stay in the engine."""

import asyncio
import contextlib

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.services.hub import RoomHub
from app.services.rooms import RoomError

router = APIRouter()


class CreateBody(BaseModel):
    nickname: str


class JoinBody(BaseModel):
    invite_code: str
    nickname: str


class TokenBody(BaseModel):
    guest_token: str


class SitBody(BaseModel):
    guest_token: str
    seat: int | None = None
    amount: int | None = None


class ChipsBody(BaseModel):
    guest_token: str
    amount: int


class BotBody(BaseModel):
    guest_token: str
    kind: str
    seat: int | None = None
    seed: int | None = None
    amount: int | None = None


class RemoveBotBody(BaseModel):
    guest_token: str
    seat: int


class PauseBody(BaseModel):
    guest_token: str
    paused: bool


class SettingsBody(BaseModel):
    guest_token: str
    small_blind: int | None = None
    big_blind: int | None = None
    seats: int | None = None
    rules: dict | None = None
    gto_mode: str | None = None
    variant: str | None = None
    tournament: dict | None = None


def _hub(request: Request) -> RoomHub:
    return request.app.state.hub


@router.post("/rooms")
async def create_room(body: CreateBody, request: Request) -> dict:
    return _hub(request).service.create(body.nickname)


@router.post("/rooms/join")
async def join_room(body: JoinBody, request: Request) -> dict:
    hub = _hub(request)
    async with hub.lock:
        created = hub.service.join(body.invite_code, body.nickname)
        hub.publish(created["room_id"])
    return created


@router.post("/rooms/{room_id}/sit")
async def sit(room_id: str, body: SitBody, request: Request) -> dict:
    return await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.sit(body.guest_token, body.seat, body.amount),
    )


@router.post("/rooms/{room_id}/stand")
async def stand(room_id: str, body: TokenBody, request: Request) -> dict:
    return await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.stand(body.guest_token),
    )


@router.post("/rooms/{room_id}/leave")
async def leave(room_id: str, body: TokenBody, request: Request) -> dict:
    return await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.leave(body.guest_token),
    )


@router.post("/rooms/{room_id}/start")
async def start_hand(room_id: str, body: TokenBody, request: Request) -> dict:
    await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.start(body.guest_token),
    )
    return {"started": True}


@router.post("/rooms/{room_id}/pause")
async def pause_table(room_id: str, body: PauseBody, request: Request) -> dict:
    await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.pause(body.guest_token, body.paused),
    )
    return {"paused": body.paused}


@router.post("/rooms/{room_id}/bots")
async def add_bot(room_id: str, body: BotBody, request: Request) -> dict:
    return await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.add_bot(
            body.guest_token,
            body.kind,
            body.seat,
            body.seed,
            amount=body.amount,
        ),
    )


@router.post("/rooms/{room_id}/bots/remove")
async def remove_bot(room_id: str, body: RemoveBotBody, request: Request) -> dict:
    return await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.remove_bot(body.guest_token, body.seat),
    )


@router.post("/rooms/{room_id}/chips")
async def add_chips(room_id: str, body: ChipsBody, request: Request) -> dict:
    return await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.add_chips(body.guest_token, body.amount),
    )


@router.post("/rooms/{room_id}/settings")
async def update_settings(room_id: str, body: SettingsBody, request: Request) -> dict:
    await _change(
        request,
        room_id,
        body.guest_token,
        lambda hub: hub.service.update_settings(
            body.guest_token,
            body.small_blind,
            body.big_blind,
            body.seats,
            body.rules,
            body.gto_mode,
            body.variant,
            body.tournament,
        ),
    )
    return {"updated": True}


@router.get("/rooms/{room_id}")
async def room_state(room_id: str, guest_token: str, request: Request) -> dict:
    _ = room_id
    return _hub(request).service.view(guest_token)


@router.websocket("/ws/room")
async def room_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    hub: RoomHub = websocket.app.state.hub
    try:
        message = await websocket.receive_json()
    except (WebSocketDisconnect, RuntimeError):
        return
    if not isinstance(message, dict) or message.get("type") != "JOIN":
        await _send_error(websocket, "first message must JOIN with guest_token")
        await _close(websocket)
        return
    payload = message.get("payload")
    token = payload.get("guest_token") if isinstance(payload, dict) else None
    try:
        async with hub.lock:
            room, member, reconnected = hub.service.connect(str(token))
            connection = hub.bind(member.token)
    except RoomError as exc:
        await _send_error(websocket, str(exc))
        await _close(websocket)
        return

    await websocket.send_json(hub.service.joined_message(room, member))
    await websocket.send_json(
        {"type": "GAME_STATE", "payload": hub.service.view(member.token)}
    )
    if reconnected:
        async with hub.lock:
            hub.service.note_reconnected(room, member)
            hub.publish(room.room_id, skip=member.token)

    async def pump() -> None:
        while connection.active:
            outgoing = await connection.queue.get()
            if not connection.active:
                break
            await websocket.send_json(outgoing)

    task = asyncio.create_task(pump())
    try:
        while True:
            incoming = await websocket.receive_json()
            await _on_client_message(hub, connection, room.room_id, incoming)
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        connection.active = False
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        hub.unbind(member.token, connection)


async def _on_client_message(hub: RoomHub, connection, room_id: str, incoming: object) -> None:
    if not isinstance(incoming, dict):
        connection.queue.put_nowait(
            {"type": "ERROR", "payload": {"message": "unsupported message"}}
        )
        return
    kind = incoming.get("type")
    request_id = incoming.get("request_id")
    payload = incoming.get("payload") if isinstance(incoming.get("payload"), dict) else {}
    try:
        async with hub.lock:
            if kind == "PLAYER_ACTION":
                hub.service.act(
                    connection.token,
                    payload.get("action"),
                    payload.get("amount"),
                    request_id,
                )
            elif kind == "RIT_VOTE":
                hub.service.vote_run_it_twice(connection.token, payload.get("accept"), request_id)
            elif kind == "INSURANCE_DECISION":
                hub.service.decide_insurance(connection.token, payload.get("accept"), request_id)
            else:
                connection.queue.put_nowait(
                    {"type": "ERROR", "payload": {"message": "unsupported message"}}
                )
                return
            hub.publish(room_id)
            hub.arm_time_bank(room_id)
    except RoomError as exc:
        connection.queue.put_nowait(
            {
                "type": "ERROR",
                "request_id": request_id,
                "payload": {"message": str(exc)},
            }
        )


async def _change(request: Request, room_id: str, token: str, action) -> dict:
    hub = _hub(request)
    async with hub.lock:
        if hub.service.room_id_for(token) != room_id:
            raise RoomError("room not found", 404)
        result = action(hub)
        hub.publish(room_id)
        hub.arm_time_bank(room_id)
    return result if isinstance(result, dict) else {"ok": True}


async def _send_error(websocket: WebSocket, message: str) -> None:
    with contextlib.suppress(RuntimeError):
        await websocket.send_json({"type": "ERROR", "payload": {"message": message}})


async def _close(websocket: WebSocket) -> None:
    with contextlib.suppress(RuntimeError):
        await websocket.close()
