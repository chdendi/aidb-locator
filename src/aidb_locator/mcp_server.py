"""MCP Server — exposes CodeLocator capabilities as MCP tools."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, ImageContent, Tool

from aidb_locator.adb import AdbClient, AdbError
from aidb_locator.commands import CodeLocator


def _build_tools() -> list[Tool]:
    return [
        Tool(
            name="aidb_grab_layout",
            description="Grab the full View hierarchy tree including Activity, Fragment info, and schemas from the connected Android device.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
            },
        ),
        Tool(
            name="aidb_edit_view",
            description="Edit a View property in real-time. Edit types: P(adding), M(argin), T(ext), TC(text color), TS(text size), A(lpha), B(ackground color), VF(view flags), LP(layout params), TXY(translation), SCXY(scale), etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "view_mem_addr": {"type": "string", "description": "View memory address (from grab_layout)"},
                    "edit_type": {"type": "string", "description": "Edit type code (e.g., T for text, P for padding)"},
                    "value": {"type": "string", "description": "New value"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["view_mem_addr", "edit_type", "value"],
            },
        ),
        Tool(
            name="aidb_get_touch_view",
            description="Find which View is at the given screen coordinates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["x", "y"],
            },
        ),
        Tool(
            name="aidb_mock_touch",
            description="Simulate a tap at the given screen coordinates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["x", "y"],
            },
        ),
        Tool(
            name="aidb_send_schema",
            description="Send a deep link (schema URL) to navigate the app.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Deep link URL (e.g., myapp://home)"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="aidb_list_files",
            description="Browse the app's file system directory tree.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
            },
        ),
        Tool(
            name="aidb_operate_file",
            description="Operate on a file in the app's filesystem (copy, move, delete).",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source file path"},
                    "target": {"type": "string", "description": "Target file path"},
                    "op": {"type": "string", "description": "Operation (copy, move, delete)"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["source", "target", "op"],
            },
        ),
        Tool(
            name="aidb_capture_view",
            description="Capture a View's rendered bitmap as a PNG image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "view_mem_addr": {"type": "string", "description": "View memory address (from grab_layout)"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["view_mem_addr"],
            },
        ),
        Tool(
            name="aidb_get_view_data",
            description="Get data bound to a View.",
            inputSchema={
                "type": "object",
                "properties": {
                    "view_mem_addr": {"type": "string", "description": "View memory address"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["view_mem_addr"],
            },
        ),
        Tool(
            name="aidb_set_view_data",
            description="Set data on a View.",
            inputSchema={
                "type": "object",
                "properties": {
                    "view_mem_addr": {"type": "string", "description": "View memory address"},
                    "data": {"type": "string", "description": "Data to set"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["view_mem_addr", "data"],
            },
        ),
        # --- Native ADB tools (no SDK needed) ---
        Tool(
            name="aidb_screenshot",
            description="Take a full-screen screenshot (no CodeLocator SDK needed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
            },
        ),
        Tool(
            name="aidb_tap",
            description="Tap at screen coordinates using native ADB input (no SDK needed, more reliable than mock_touch).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["x", "y"],
            },
        ),
        Tool(
            name="aidb_swipe",
            description="Swipe from one point to another (no SDK needed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x1": {"type": "integer", "description": "Start X"},
                    "y1": {"type": "integer", "description": "Start Y"},
                    "x2": {"type": "integer", "description": "End X"},
                    "y2": {"type": "integer", "description": "End Y"},
                    "duration_ms": {"type": "integer", "description": "Duration in milliseconds (default 300)"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
        ),
        Tool(
            name="aidb_dump_ui",
            description="Dump UI hierarchy as XML via uiautomator (no SDK needed). Provides accessibility-level View info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
            },
        ),
        Tool(
            name="aidb_top_activity",
            description="Get the current top Activity name (no SDK needed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
            },
        ),
        Tool(
            name="aidb_key",
            description="Send a key event (e.g., BACK=4, HOME=3, ENTER=66) (no SDK needed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "keycode": {"type": ["integer", "string"], "description": "Key code number or name (BACK, HOME, ENTER)"},
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
                "required": ["keycode"],
            },
        ),
        Tool(
            name="aidb_screen_size",
            description="Get device screen resolution (no SDK needed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device serial (optional)"},
                },
            },
        ),
    ]


def _make_locator(args: dict, default_serial: str | None = None) -> CodeLocator:
    serial = args.get("device") or default_serial
    return CodeLocator(AdbClient(device_serial=serial))


def _make_native(args: dict, default_serial: str | None = None):
    from aidb_locator.commands import NativeAdb
    serial = args.get("device") or default_serial
    return NativeAdb(AdbClient(device_serial=serial))


def run_server(device_serial: str | None = None):
    """Run the MCP server with stdio transport."""
    import asyncio

    server = Server("aidb-locator")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _build_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
        try:
            locator = _make_locator(arguments, device_serial)

            if name == "aidb_grab_layout":
                app = locator.grab_layout()
                return [TextContent(type="text", text=json.dumps(app.to_dict(), indent=2, ensure_ascii=False))]

            elif name == "aidb_edit_view":
                ok = locator.edit_view(arguments["view_mem_addr"], arguments["edit_type"], arguments["value"])
                return [TextContent(type="text", text=json.dumps({"success": ok}))]

            elif name == "aidb_get_touch_view":
                view = locator.get_touch_view(arguments["x"], arguments["y"])
                return [TextContent(type="text", text=json.dumps(view.to_dict(), indent=2, ensure_ascii=False))]

            elif name == "aidb_mock_touch":
                ok = locator.mock_touch(arguments["x"], arguments["y"])
                return [TextContent(type="text", text=json.dumps({"success": ok}))]

            elif name == "aidb_send_schema":
                result = locator.send_schema(arguments["url"])
                return [TextContent(type="text", text=json.dumps({"result": result}))]

            elif name == "aidb_list_files":
                tree = locator.list_files()
                return [TextContent(type="text", text=json.dumps(tree.to_dict(), indent=2, ensure_ascii=False))]

            elif name == "aidb_operate_file":
                ok = locator.operate_file(arguments["source"], arguments["target"], arguments["op"])
                return [TextContent(type="text", text=json.dumps({"success": ok}))]

            elif name == "aidb_capture_view":
                path = Path(locator.capture_view(arguments["view_mem_addr"]))
                try:
                    img_data = base64.b64encode(path.read_bytes()).decode("ascii")
                finally:
                    path.unlink(missing_ok=True)
                return [ImageContent(type="image", data=img_data, mimeType="image/png")]

            elif name == "aidb_get_view_data":
                data = locator.get_view_data(arguments["view_mem_addr"])
                return [TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))]

            elif name == "aidb_set_view_data":
                ok = locator.set_view_data(arguments["view_mem_addr"], arguments["data"])
                return [TextContent(type="text", text=json.dumps({"success": ok}))]

            # --- Native ADB tools ---
            elif name == "aidb_screenshot":
                native = _make_native(arguments, device_serial)
                path = Path(native.screenshot())
                try:
                    img_data = base64.b64encode(path.read_bytes()).decode("ascii")
                finally:
                    path.unlink(missing_ok=True)
                return [ImageContent(type="image", data=img_data, mimeType="image/png")]

            elif name == "aidb_tap":
                native = _make_native(arguments, device_serial)
                native.tap(arguments["x"], arguments["y"])
                return [TextContent(type="text", text=json.dumps({"success": True, "x": arguments["x"], "y": arguments["y"]}))]

            elif name == "aidb_swipe":
                native = _make_native(arguments, device_serial)
                duration = arguments.get("duration_ms", 300)
                native.swipe(arguments["x1"], arguments["y1"], arguments["x2"], arguments["y2"], duration)
                return [TextContent(type="text", text=json.dumps({"success": True}))]

            elif name == "aidb_dump_ui":
                native = _make_native(arguments, device_serial)
                xml = native.dump_ui()
                return [TextContent(type="text", text=xml)]

            elif name == "aidb_top_activity":
                native = _make_native(arguments, device_serial)
                info = native.top_activity()
                return [TextContent(type="text", text=json.dumps(info, indent=2))]

            elif name == "aidb_key":
                native = _make_native(arguments, device_serial)
                keycode = arguments["keycode"]
                key_map = {"BACK": 4, "HOME": 3, "ENTER": 66, "TAB": 61, "MENU": 82, "POWER": 26}
                if isinstance(keycode, str):
                    keycode = key_map.get(keycode.upper(), keycode)
                native.input_keyevent(keycode)
                return [TextContent(type="text", text=json.dumps({"success": True, "keycode": keycode}))]

            elif name == "aidb_screen_size":
                native = _make_native(arguments, device_serial)
                size = native.screen_size()
                return [TextContent(type="text", text=json.dumps(size))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except AdbError as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def _run():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_run())
