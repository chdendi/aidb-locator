"""Snapshot endpoints — combine screenshot + layout + activity."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import Response

from aidb_locator.commands import CodeLocator, NativeAdb
from aidb_locator.models import WApplication, WView
from aidb_locator.ui.deps import make_codelocator, make_native

router = APIRouter()


def _view_to_full_dict(v: WView, parent_content_left: int = 0, parent_content_top: int = 0) -> dict:
    """Serialize WView with screen-absolute bounds.

    CodeLocator returns parent-relative `getLeft/Top/Right/Bottom()`. To turn
    these into where the view is actually drawn on screen we need to also
    account for two things every parent does on the way down:

      - `scrollX/Y`: shifts the parent's children opposite to the scroll. A
        ViewPager whose `scrollX = 2432` draws its child at layout x=2432
        starting at screen x=0. Without this, items inside any horizontal
        scroller / pager not on page 0 land off-screen in the hit-test.
      - `translationX/Y`: shifts the view itself from its layout position
        without changing layout (used by page transformers, animations).

    So for each view:
        screen_left = parent_content_left + v.left + v.translation_x
        next children's content_origin = screen_left - v.scroll_x
    """
    abs_left = parent_content_left + v.left + int(round(v.translation_x))
    abs_top = parent_content_top + v.top + int(round(v.translation_y))
    width = v.right - v.left
    height = v.bottom - v.top
    abs_right = abs_left + width
    abs_bottom = abs_top + height

    child_content_left = abs_left - v.scroll_x
    child_content_top = abs_top - v.scroll_y

    return {
        "class_name": v.class_name,
        "visibility": v.visibility,
        "id_str": v.id_str,
        "mem_addr": v.mem_addr,
        "text": v.text,
        "bounds": {"left": abs_left, "top": abs_top, "right": abs_right, "bottom": abs_bottom},
        "padding": [v.padding_left, v.padding_top, v.padding_right, v.padding_bottom],
        "margin": [v.margin_left, v.margin_top, v.margin_right, v.margin_bottom],
        "alpha": v.alpha,
        "background_color": v.background_color,
        "text_color": v.text_color,
        "text_size": v.text_size,
        "is_clickable": v.is_clickable,
        "children": [_view_to_full_dict(c, child_content_left, child_content_top) for c in v.children],
    }


def _activity_block(app: WApplication) -> dict:
    return {
        "activity": app.activity.class_name,
        "package": app.package_name,
        "fragments": [f.class_name for f in app.activity.fragments if f.is_visible or f.is_added],
    }


def _root_view(app: WApplication) -> WView | None:
    return app.activity.decor_views[0] if app.activity.decor_views else None


@router.get("/snapshot")
async def snapshot(device: str | None = Query(default=None)) -> dict:
    cl = make_codelocator(device)
    nat = make_native(device)

    # Wait for both calls so a layout failure still leaves the screenshot path
    # available for cleanup. screenshot() deletes its own temp file if capture fails.
    layout_result, shot_result = await asyncio.gather(
        asyncio.to_thread(cl.grab_layout),
        asyncio.to_thread(nat.screenshot),
        return_exceptions=True,
    )
    png_path = None if isinstance(shot_result, BaseException) else Path(shot_result)
    try:
        if isinstance(layout_result, BaseException):
            if isinstance(shot_result, BaseException):
                raise layout_result from shot_result
            raise layout_result
        if isinstance(shot_result, BaseException):
            raise shot_result
        if png_path is None:
            raise RuntimeError("screenshot path missing")
        png_bytes = png_path.read_bytes()
    finally:
        if png_path is not None:
            png_path.unlink(missing_ok=True)

    app = layout_result
    root = _root_view(app)
    return {
        "screenshot_png_b64": base64.b64encode(png_bytes).decode("ascii"),
        "device_size": {"width": app.screen_width, "height": app.screen_height},
        "density": app.density,
        "activity": _activity_block(app),
        "layout": _view_to_full_dict(root) if root else None,
        "schemas": [s.schema for s in app.schemas],
    }


@router.get("/screenshot")
def screenshot_png(device: str | None = Query(default=None)) -> Response:
    path = Path(make_native(device).screenshot())
    try:
        data = path.read_bytes()
    finally:
        path.unlink(missing_ok=True)
    return Response(content=data, media_type="image/png")


@router.get("/layout")
def layout(device: str | None = Query(default=None)) -> dict:
    app = make_codelocator(device).grab_layout()
    root = _root_view(app)
    return _view_to_full_dict(root) if root else {}


@router.get("/activity")
def activity(device: str | None = Query(default=None)) -> dict:
    app = make_codelocator(device).grab_layout()
    return _activity_block(app)
