from __future__ import annotations

from fastapi import FastAPI
from uvicorn import Config, Server


async def run_web_server(app: FastAPI, *, host: str, port: int, log_level: str) -> None:
    config = Config(
        app=app,
        host=host,
        port=port,
        loop="asyncio",
        proxy_headers=True,
        log_level=log_level.lower(),
    )
    server = Server(config)
    await server.serve()
