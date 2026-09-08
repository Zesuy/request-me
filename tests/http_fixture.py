"""Offline integration fixture. Never load this module in the production server."""
import socket

import uvicorn
from fastapi import HTTPException

from server.app import create_app
from server.core import RequestError


class Sender:
    async def send_request(self, message):
        return "mock-qq-" + message.request_id

    async def send_notification(self, message):
        return "mock-notify-" + message.request_id


app = create_app(sender=Sender(), bridges={"one": "token-one", "two": "token-two"})


@app.post("/test/answer")
async def answer(payload: dict):
    try:
        result = await app.state.request_service.handle_manual(payload["bridge"], payload["text"])
        return {"id": result.id}
    except RequestError as error:
        raise HTTPException(error.status, error.message)


if __name__ == "__main__":
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1], flush=True)
    uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off")).run(sockets=[listener])
