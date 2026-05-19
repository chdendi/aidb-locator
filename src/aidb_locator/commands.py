"""High-level API for CodeLocator capabilities."""

from __future__ import annotations

import json
import struct
import tempfile
import zlib
from pathlib import Path

from aidb_locator.adb import AdbClient, AdbError
from aidb_locator.models import (
    WApplication,
    WFile,
    WView,
    parse_application,
)
from aidb_locator.protocol import (
    ACTION_CHANGE_VIEW,
    ACTION_DEBUG_FILE_INFO,
    ACTION_DEBUG_FILE_OP,
    ACTION_GET_TOUCH_VIEW,
    ACTION_LAYOUT_INFO,
    ACTION_MOCK_TOUCH_VIEW,
    ACTION_PROCESS_SCHEMA,
    EDIT_GET_DATA,
    EDIT_SET_DATA,
    EDIT_VIEW_BITMAP,
    KEY_CHANGE_VIEW,
    KEY_DATA,
    KEY_FILE_OPERATE,
    KEY_MOCK_CLICK_X,
    KEY_MOCK_CLICK_Y,
    KEY_SOURCE_PATH,
    KEY_TARGET_PATH,
    RESULT_IMAGE_PATH,
    decode_inline_result,
    decode_file_result,
    extract_result_data,
)


class CodeLocator:
    def __init__(self, adb: AdbClient):
        self._adb = adb

    def _send(self, action: str, args: dict[str, str] | None = None) -> dict:
        """Send broadcast and parse response."""
        raw = self._adb.broadcast(action, args)
        data_str, is_file = extract_result_data(raw)

        if data_str is None:
            return {"code": -1, "msg": "No data in response"}

        if is_file:
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
                local = self._adb.pull(data_str, tmp.name)
                content = local.read_bytes()
            return decode_file_result(content)

        return decode_inline_result(data_str)

    def grab_layout(self) -> WApplication:
        """Grab full layout info: View tree, Activity, Fragments, Schemas."""
        response = self._send(ACTION_LAYOUT_INFO)
        return parse_application(response)

    def edit_view(self, view_mem_addr: str, edit_type: str, value: str) -> bool:
        """Edit a View property by memory address (hex identityHashCode)."""
        operate_data = self._build_operate_data(view_mem_addr, edit_type, value)
        response = self._send(ACTION_CHANGE_VIEW, {KEY_CHANGE_VIEW: operate_data})
        return response.get("code", -1) == 0

    def get_touch_view(self, x: int, y: int) -> WView:
        """Get the View at the given touch coordinates."""
        response = self._send(
            ACTION_GET_TOUCH_VIEW,
            {KEY_MOCK_CLICK_X: str(x), KEY_MOCK_CLICK_Y: str(y)},
        )
        data = response.get("data", {})
        if isinstance(data, list):
            data = data[0] if data else {}
        return WView.from_dict(data)

    def mock_touch(self, x: int, y: int) -> bool:
        """Simulate a touch event at the given coordinates."""
        response = self._send(
            ACTION_MOCK_TOUCH_VIEW,
            {KEY_MOCK_CLICK_X: str(x), KEY_MOCK_CLICK_Y: str(y)},
        )
        return response.get("code", -1) == 0

    def send_schema(self, url: str) -> str:
        """Send a deep link (schema) to the app."""
        response = self._send(ACTION_PROCESS_SCHEMA, {KEY_DATA: url})
        return response.get("msg", "")

    def list_files(self) -> WFile:
        """List the app's file system tree."""
        response = self._send(ACTION_DEBUG_FILE_INFO)
        return WFile.from_dict(response.get("data", {}))

    def operate_file(self, source: str, target: str, op: str) -> bool:
        """Operate on a file (copy, move, delete, etc.)."""
        response = self._send(
            ACTION_DEBUG_FILE_OP,
            {KEY_SOURCE_PATH: source, KEY_TARGET_PATH: target, KEY_FILE_OPERATE: op},
        )
        return response.get("code", -1) == 0

    def _build_operate_data(self, view_mem_addr: str, edit_type: str, args: str = "") -> str:
        """Build OperateData JSON for change view actions."""
        import json as _json
        item_id = int(view_mem_addr, 16)
        return _json.dumps({
            "aa": "V",
            "d4": item_id,
            "d5": [{"d7": edit_type, "d8": args}],
        })

    def capture_view(self, view_mem_addr: str, output: str | Path | None = None) -> Path:
        """Capture a View's rendered bitmap."""
        operate_data = self._build_operate_data(view_mem_addr, EDIT_VIEW_BITMAP)
        self._send(ACTION_CHANGE_VIEW, {KEY_CHANGE_VIEW: operate_data})

        if output is None:
            output = Path(tempfile.mktemp(suffix=".png"))
        output = Path(output)
        return self._adb.pull(RESULT_IMAGE_PATH, output)

    def get_view_data(self, view_mem_addr: str) -> dict:
        """Get data bound to a View."""
        operate_data = self._build_operate_data(view_mem_addr, EDIT_GET_DATA)
        response = self._send(ACTION_CHANGE_VIEW, {KEY_CHANGE_VIEW: operate_data})
        data = response.get("data", "")
        if isinstance(data, str):
            try:
                return json.loads(data)
            except (json.JSONDecodeError, TypeError):
                return {"raw": data}
        return data if isinstance(data, dict) else {"raw": str(data)}

    def set_view_data(self, view_mem_addr: str, data: str) -> bool:
        """Set data on a View."""
        operate_data = self._build_operate_data(view_mem_addr, EDIT_SET_DATA, data)
        response = self._send(ACTION_CHANGE_VIEW, {KEY_CHANGE_VIEW: operate_data})
        return response.get("code", -1) == 0


class NativeAdb:
    """Native ADB commands that work without CodeLocator SDK."""

    def __init__(self, adb: AdbClient):
        self._adb = adb

    def screenshot(self, output: str | Path | None = None) -> Path:
        """Take a full-screen screenshot."""
        remote = "/sdcard/aidb_screenshot.png"
        self._adb.shell(f"screencap -p {remote}")
        if output is None:
            output = Path(tempfile.mktemp(suffix=".png"))
        local = self._adb.pull(remote, Path(output))
        if _png_is_fully_transparent(local):
            try:
                return self._adb.emulator_screenshot(local)
            except AdbError:
                return local
        return local

    def tap(self, x: int, y: int) -> None:
        """Tap at screen coordinates."""
        self._adb.shell(f"input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """Swipe from (x1,y1) to (x2,y2)."""
        self._adb.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def input_text(self, text: str) -> None:
        """Input text (ASCII only)."""
        escaped = text.replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>")
        self._adb.shell(f"input text '{escaped}'")

    def input_keyevent(self, keycode: int | str) -> None:
        """Send a key event (e.g., 3=HOME, 4=BACK, 24=VOLUME_UP)."""
        self._adb.shell(f"input keyevent {keycode}")

    def dump_ui(self) -> str:
        """Dump UI hierarchy via uiautomator (no SDK needed)."""
        remote = "/sdcard/aidb_uidump.xml"
        self._adb.shell(f"uiautomator dump {remote}")
        local = Path(tempfile.mktemp(suffix=".xml"))
        self._adb.pull(remote, local)
        return local.read_text(encoding="utf-8")

    def top_activity(self) -> dict:
        """Get the current top activity info."""
        output = self._adb.shell("dumpsys activity top | head -5")
        result: dict = {}
        for line in output.strip().splitlines():
            line = line.strip()
            if "ACTIVITY" in line:
                parts = line.split()
                for p in parts:
                    if "/" in p:
                        pkg, act = p.split("/", 1)
                        result["package"] = pkg
                        result["activity"] = act
                        break
        return result

    def open_deeplink(self, url: str) -> str:
        """Open a deep link via am start."""
        return self._adb.shell(
            f"am start -a android.intent.action.VIEW -d '{url}'"
        )

    def screen_size(self) -> dict:
        """Get screen resolution."""
        output = self._adb.shell("wm size")
        for line in output.strip().splitlines():
            if "Physical size" in line or "Override size" in line:
                size = line.split(":")[-1].strip()
                w, h = size.split("x")
                return {"width": int(w), "height": int(h)}
        return {"width": 0, "height": 0}


def _png_is_fully_transparent(path: str | Path) -> bool:
    """Return True for 8-bit RGBA PNGs whose alpha channel is all zero."""
    try:
        raw = Path(path).read_bytes()
        width, height, color_type, bit_depth, interlace, idat = _parse_png(raw)
        if color_type != 6 or bit_depth != 8 or interlace != 0:
            return False
        data = zlib.decompress(idat)
        row_len = width * 4
        pos = 0
        prev = bytes(row_len)
        for _ in range(height):
            filter_type = data[pos]
            pos += 1
            row = bytearray(data[pos:pos + row_len])
            pos += row_len
            _unfilter_png_row(row, prev, 4, filter_type)
            if any(alpha != 0 for alpha in row[3::4]):
                return False
            prev = bytes(row)
        return True
    except Exception:
        return False


def _parse_png(raw: bytes) -> tuple[int, int, int, int, int, bytes]:
    signature = b"\x89PNG\r\n\x1a\n"
    if not raw.startswith(signature):
        raise ValueError("not a png")

    pos = len(signature)
    width = height = color_type = bit_depth = interlace = None
    idat_parts: list[bytes] = []
    while pos + 8 <= len(raw):
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        chunk_type = raw[pos + 4:pos + 8]
        pos += 8
        chunk = raw[pos:pos + length]
        pos += length + 4  # skip data and CRC

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None:
        raise ValueError("png missing IHDR")
    return width, height, color_type, bit_depth, interlace, b"".join(idat_parts)


def _unfilter_png_row(row: bytearray, prev: bytes, bpp: int, filter_type: int) -> None:
    if filter_type == 0:
        return
    if filter_type == 1:
        for i in range(len(row)):
            row[i] = (row[i] + (row[i - bpp] if i >= bpp else 0)) & 0xFF
        return
    if filter_type == 2:
        for i in range(len(row)):
            row[i] = (row[i] + prev[i]) & 0xFF
        return
    if filter_type == 3:
        for i in range(len(row)):
            left = row[i - bpp] if i >= bpp else 0
            up = prev[i]
            row[i] = (row[i] + ((left + up) // 2)) & 0xFF
        return
    if filter_type == 4:
        for i in range(len(row)):
            left = row[i - bpp] if i >= bpp else 0
            up = prev[i]
            up_left = prev[i - bpp] if i >= bpp else 0
            row[i] = (row[i] + _paeth_predictor(left, up, up_left)) & 0xFF
        return
    raise ValueError(f"unsupported PNG filter: {filter_type}")


def _paeth_predictor(left: int, up: int, up_left: int) -> int:
    p = left + up - up_left
    pa = abs(p - left)
    pb = abs(p - up)
    pc = abs(p - up_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return up_left
