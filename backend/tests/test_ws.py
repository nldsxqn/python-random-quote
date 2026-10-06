from app.main import app
from fastapi.testclient import TestClient


def test_websocket_sends_connected() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            message = websocket.receive_json()

    assert message == {
        "type": "CONNECTED",
        "payload": {"service": "openpokerlab"},
    }
