"""A total size limit for resume uploads, enforced while the request streams in (LLD §6.2, HLD §15).

The per-file checks (20 MB, %PDF-) run after Starlette has parsed the multipart body and copied
each file to a temporary file. On their own, 20 files of 20 MB would make one 400 MB request.
This middleware stops a `POST /background-jobs/resume` request as soon as it exceeds
`MAX_UPLOAD_REQUEST_MB`:

- a declared `Content-Length` over the limit is refused before a single byte is read;
- otherwise the bytes are counted as they arrive, and reading stops at the limit, so at most
  that much is ever spooled.

The answer is 422 with the usual error envelope, like the other whole-request upload errors
(the API does not use 413, LLD §4.4), and the connection is closed, so the client stops sending.
Nothing is stored and no job is created.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.errors import error_response

UPLOAD_PATH = "/background-jobs/resume"
MB = 1024 * 1024


def too_large_response(limit_mb: int) -> JSONResponse:
    message = f"the upload is larger than {limit_mb} MB in total (MAX_UPLOAD_REQUEST_MB); send fewer or smaller files"
    response = error_response(422, "VALIDATION_ERROR", "The request is not valid.",
                              {"errors": [{"field": "body", "message": message}]})
    # Close the connection after answering. Otherwise Uvicorn would keep reading (and discarding)
    # the rest of the oversized body, just to reuse the connection for another request.
    response.headers["Connection"] = "close"
    return response


class RequestTooLarge(HTTPException):
    """Raised while the body is being read. FastAPI passes an HTTPException from body parsing
    through unchanged, so `handle_request_too_large` answers instead of a generic 400."""

    def __init__(self, limit_mb: int):
        super().__init__(status_code=422)
        self.limit_mb = limit_mb


async def handle_request_too_large(_: Request, exc: RequestTooLarge) -> JSONResponse:
    return too_large_response(exc.limit_mb)


class UploadSizeLimit:
    """ASGI middleware: only `POST /background-jobs/resume` is limited; other requests pass untouched."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") != UPLOAD_PATH:
            await self.app(scope, receive, send)
            return

        limit_mb = get_settings().max_upload_request_mb
        limit = limit_mb * MB
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await too_large_response(limit_mb)(scope, receive, send)  # nothing has been read
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestTooLarge(limit_mb)  # stop reading: the rest is never spooled
            return message

        await self.app(scope, counting_receive, send)
