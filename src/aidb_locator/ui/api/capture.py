"""GET /api/capture/{view_addr} — single-view rendered bitmap."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response

from aidb_locator.commands import CodeLocator
from aidb_locator.ui.deps import make_codelocator

router = APIRouter()


def _content_disposition(filename: str) -> str:
    """Match Starlette FileResponse's attachment header."""
    quoted = quote(filename)
    if quoted != filename:
        return f"attachment; filename*=utf-8''{quoted}"
    return f'attachment; filename="{filename}"'


@router.get("/capture/{view_addr}")
def capture(view_addr: str, device: str | None = Query(default=None)) -> Response:
    path = Path(make_codelocator(device).capture_view(view_addr))
    try:
        data = path.read_bytes()
    finally:
        path.unlink(missing_ok=True)
    filename = f"view_{view_addr}.png"
    return Response(
        content=data,
        media_type="image/png",
        headers={"content-disposition": _content_disposition(filename)},
    )
