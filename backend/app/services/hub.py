"""Fan-out for one server process. Each connection gets its own rendered view."""

import asyncio
from dataclasses import dataclass, field

from app.history.store import HandHistory
from app.rules.clock import SystemClock
from app.services.rooms import RoomService


@dataclass
class Connection:
    token: str
    active: bool = True
    queue: asyncio.Queue[dict] = field(default_factory=asyncio.Queue)


class RoomHub:
    def __init__(self, history: HandHistory | None = None) -> None:
        self.service = RoomService(history=history)
        self.connections: dict[str, Connection] = {}
        self.lock = asyncio.Lock()

    def bind(self, token: str) -> Connection:
        previous = self.connections.get(token)
        if previous is not None:
            previous.active = False
        connection = Connection(token=token)
        self.connections[token] = connection
        return connection

    def unbind(self, token: str, connection: Connection) -> None:
        connection.active = False
        current = self.connections.get(token)
        if current is connection:
            self.connections.pop(token, None)
            self.service.mark_disconnected(token)

    def publish(self, room_id: str, skip: str | None = None) -> None:
        room = self.service.rooms.get(room_id)
        if room is None:
            return
        events = self.service.pull_events(room)
        for token, member in list(room.members.items()):
            if token == skip:
                continue
            connection = self.connections.get(token)
            if connection is None or not connection.active or not member.connected:
                continue
            for event in events:
                connection.queue.put_nowait(self.service.render(room, member, event))
        self.service.discard_if_closed(room_id)

    def arm_time_bank(self, room_id: str) -> None:
        """Sleep only for the production clock. Tests advance ManualClock themselves."""
        room = self.service.rooms.get(room_id)
        if room is None or room.action_deadline is None:
            return
        if not isinstance(room.clock, SystemClock):
            return
        deadline = room.action_deadline
        delay = max(0.0, deadline - room.clock.now())

        async def _fire() -> None:
            await asyncio.sleep(delay)
            async with self.lock:
                current = self.service.rooms.get(room_id)
                if current is None or current.action_deadline != deadline:
                    return
                if not self.service.resolve_time_bank(room_id):
                    return
                self.publish(room_id)
                self.arm_time_bank(room_id)

        asyncio.get_running_loop().create_task(_fire())
