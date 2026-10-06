from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.history_routes import router as history_router
from app.api.room_routes import router
from app.api.settings_routes import router as settings_router
from app.api.solver_routes import router as solver_router
from app.api.study_routes import router as study_router
from app.config.settings import LAN_ORIGIN_REGEX, get_settings
from app.database.migrate import upgrade_database
from app.db import create_db_engine, database_status
from app.history.store import HandHistory
from app.services.hub import RoomHub
from app.services.rooms import RoomError
from app.solver.jobs import AnalysisStore

settings = get_settings()
engine = create_db_engine(settings.database_url)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upgrade_database(settings.database_url)
    yield


app = FastAPI(title="OpenPokerLab", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(history_router)
app.include_router(settings_router)
app.include_router(solver_router)
app.include_router(study_router)
app.state.history = HandHistory(engine)
app.state.analysis = AnalysisStore(engine)
app.state.hub = RoomHub(history=app.state.history)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=LAN_ORIGIN_REGEX,
    allow_credentials=True,
    allow_private_network=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RoomError)
async def room_error_handler(_request: Request, exc: RoomError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"type": "ERROR", "payload": {"message": str(exc)}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "openpokerlab",
        "database": database_status(engine),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "CONNECTED", "payload": {"service": "openpokerlab"}})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
