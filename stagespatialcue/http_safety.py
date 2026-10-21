"""Limit request bytes as ASGI receives them, before multipart spooling."""
from fastapi import HTTPException
from starlette.responses import PlainTextResponse


class RequestSizeLimit:
    def __init__(self, app, max_bytes: int = 256 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get('headers', []))
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            await PlainTextResponse('Invalid Content-Length', status_code=400)(scope, receive, send)
            return
        if length < 0 or length > self.max_bytes:
            await PlainTextResponse('Request exceeds 256 MiB; split the upload batch', status_code=413)(scope, receive, send)
            return
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            if message['type'] == 'http.request':
                consumed += len(message.get('body', b''))
                if consumed > self.max_bytes:
                    # FastAPI/Starlette's route exception boundary returns 413.
                    raise HTTPException(413, 'Request exceeds 256 MiB; split the upload batch')
            return message

        await self.app(scope, bounded_receive, send)
