"""
Request body size limit (pure ASGI middleware).

Bounds the bytes the server will read for one request before any route,
validation or paid work runs (review 2026-11-20, finding 2). Both a declared
Content-Length and the bytes actually streamed (chunked bodies) are checked.

Environment:
  MAX_REQUEST_BODY_BYTES - maximum request body size in bytes (default 262144)
"""

from __future__ import annotations

import json
import os

from fastapi import HTTPException

MAX_REQUEST_BODY_BYTES = int(os.environ.get("MAX_REQUEST_BODY_BYTES", "262144"))
BODY_TOO_LARGE_DETAIL = "Request body too large"


class RequestBodyTooLarge(HTTPException):
    """Raised from the wrapped receive(); FastAPI re-raises HTTPException as-is."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=BODY_TOO_LARGE_DETAIL)


async def _send_413(send) -> None:
    body = json.dumps({"detail": BODY_TOO_LARGE_DETAIL}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int | None = None):
        self.app = app
        self.max_bytes = max_bytes

    def _limit(self) -> int:
        return int(self.max_bytes if self.max_bytes is not None else MAX_REQUEST_BODY_BYTES)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit()
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                text = value.decode("latin-1").strip()
                if text.isdigit() and int(text) > limit:
                    await _send_413(send)
                    return
                break

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body") or b"")
                if received > limit:
                    raise RequestBodyTooLarge()
            return message

        async def tracking_send(message):
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLarge:
            if started:
                raise
            await _send_413(send)
