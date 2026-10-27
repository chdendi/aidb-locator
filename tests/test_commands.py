from __future__ import annotations

import base64
import json
import shlex
import struct
import tempfile
import zlib
from pathlib import Path
from unittest.mock import MagicMock

from aidb_locator.adb import AdbClient, AdbError, shell_join
from aidb_locator.commands import CodeLocator, NativeAdb
from aidb_locator.models import WApplication


def _make_broadcast_output(data: dict) -> str:
    """Helper: wrap a dict into a broadcast inline result string."""
    json_str = json.dumps(data)
    compressed = zlib.compress(json_str.encode("utf-8"))
    b64 = base64.b64encode(compressed).decode("ascii")
    return f'Broadcasting: ...\nresult=0\ndata="{b64}"'


def _rgba_png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    scanlines = b"".join(
        b"\x00" + rgba[y * width * 4:(y + 1) * width * 4]
        for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


class TestGrabLayout:
    def test_grab_layout_returns_application(self):
        app_data = {
            "code": 0,
            "data": {
                "bd": "com.example.app",
                "b7": {
                    "ag": "com.example.MainActivity",
                    "cj": [{"ag": "FrameLayout", "ab": "V", "d": 0, "e": 1080, "f": 0, "g": 2340}],
                    "ck": [{"ag": "HomeFragment", "cd": True, "ce": True}],
                },
                "bc": [],
            },
        }
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.broadcast.return_value = _make_broadcast_output(app_data)

        locator = CodeLocator(mock_adb)
        result = locator.grab_layout()

        assert isinstance(result, WApplication)
        assert result.package_name == "com.example.app"
        assert result.activity.class_name == "com.example.MainActivity"
        assert len(result.activity.fragments) == 1


class TestGetTouchView:
    def test_get_touch_view(self):
        view_data = {
            "code": 0,
            "data": {
                "ag": "android.widget.Button",
                "ab": "V",
                "ac": "submit_btn",
                "d": 100, "e": 300, "f": 500, "g": 580,
            },
        }
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.broadcast.return_value = _make_broadcast_output(view_data)

        locator = CodeLocator(mock_adb)
        view = locator.get_touch_view(200, 540)

        assert view.class_name == "android.widget.Button"
        assert view.id_str == "submit_btn"


class TestMockTouch:
    def test_mock_touch_success(self):
        result_data = {"code": 0, "msg": "success"}
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.broadcast.return_value = _make_broadcast_output(result_data)

        locator = CodeLocator(mock_adb)
        assert locator.mock_touch(540, 960) is True


class TestSendSchema:
    def test_send_schema(self):
        result_data = {"code": 0, "msg": "success", "data": "navigated"}
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.broadcast.return_value = _make_broadcast_output(result_data)

        locator = CodeLocator(mock_adb)
        result = locator.send_schema("myapp://home")
        assert result is not None


class TestEditView:
    def test_edit_view_text(self):
        result_data = {"code": 0, "msg": "success"}
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.broadcast.return_value = _make_broadcast_output(result_data)

        locator = CodeLocator(mock_adb)
        assert locator.edit_view("0x1234", "T", "New Text") is True


class TestNativeScreenshot:
    def test_screenshot_falls_back_when_screencap_times_out(self, tmp_path):
        fallback = _rgba_png(1, 1, bytes([255, 0, 0, 255]))
        output = tmp_path / "shot.png"
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.shell.side_effect = AdbError("ADB command timed out")

        def fake_emulator_screenshot(local):
            local.write_bytes(fallback)
            return local

        mock_adb.emulator_screenshot.side_effect = fake_emulator_screenshot

        result = NativeAdb(mock_adb).screenshot(output)

        assert result == output
        assert output.read_bytes() == fallback
        mock_adb.pull.assert_not_called()
        mock_adb.emulator_screenshot.assert_called_once_with(output)

    def test_screenshot_reraises_screencap_error_when_emulator_fallback_fails(self, tmp_path):
        output = tmp_path / "shot.png"
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.shell.side_effect = AdbError("ADB command timed out")
        mock_adb.emulator_screenshot.side_effect = AdbError("not an emulator")

        try:
            NativeAdb(mock_adb).screenshot(output)
            assert False, "Should have raised AdbError"
        except AdbError as e:
            assert "timed out" in str(e)

        mock_adb.pull.assert_not_called()
        mock_adb.emulator_screenshot.assert_called_once_with(output)

    def test_screenshot_falls_back_for_fully_transparent_png(self, tmp_path):
        transparent = _rgba_png(2, 1, bytes([0, 0, 0, 0, 0, 0, 0, 0]))
        fallback = _rgba_png(2, 1, bytes([255, 0, 0, 255, 0, 255, 0, 255]))
        output = tmp_path / "shot.png"
        mock_adb = MagicMock(spec=AdbClient)

        def fake_pull(remote, local):
            local.write_bytes(transparent)
            return local

        def fake_emulator_screenshot(local):
            local.write_bytes(fallback)
            return local

        mock_adb.pull.side_effect = fake_pull
        mock_adb.emulator_screenshot.side_effect = fake_emulator_screenshot

        result = NativeAdb(mock_adb).screenshot(output)

        assert result == output
        assert output.read_bytes() == fallback
        mock_adb.shell.assert_called_once_with("screencap -p /sdcard/aidb_screenshot.png")
        mock_adb.pull.assert_called_once()
        mock_adb.emulator_screenshot.assert_called_once_with(output)

    def test_screenshot_keeps_normal_png(self, tmp_path):
        normal = _rgba_png(1, 1, bytes([1, 2, 3, 255]))
        output = tmp_path / "shot.png"
        mock_adb = MagicMock(spec=AdbClient)

        def fake_pull(remote, local):
            local.write_bytes(normal)
            return local

        mock_adb.pull.side_effect = fake_pull

        result = NativeAdb(mock_adb).screenshot(output)

        assert result == output
        assert output.read_bytes() == normal
        mock_adb.emulator_screenshot.assert_not_called()


class TestShellArgumentQuoting:
    def test_input_text_encodes_spaces(self):
        mock_adb = MagicMock(spec=AdbClient)
        NativeAdb(mock_adb).input_text("hello world")
        mock_adb.shell.assert_called_once_with("input text hello%sworld")

    def test_input_text_quotes_quotes_and_metacharacters(self):
        mock_adb = MagicMock(spec=AdbClient)
        NativeAdb(mock_adb).input_text("it's a & b;$(id)<tag>")
        encoded = "it's a & b;$(id)<tag>".replace(" ", "%s")
        mock_adb.shell.assert_called_once_with("input text " + shlex.quote(encoded))
        command = mock_adb.shell.call_args[0][0]
        assert "\\&" not in command
        assert command == shell_join(["input", "text", encoded])

    def test_open_deeplink_quotes_url(self):
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.shell.return_value = "ok"
        url = "myapp://path?q=a b&x='y'"
        NativeAdb(mock_adb).open_deeplink(url)
        mock_adb.shell.assert_called_once_with(
            shell_join(["am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        )

    def test_keyevent_quotes_unsafe_keycode_and_leaves_numbers(self):
        mock_adb = MagicMock(spec=AdbClient)
        native = NativeAdb(mock_adb)
        native.input_keyevent(4)
        native.input_keyevent("4;reboot")
        assert mock_adb.shell.call_args_list[0].args[0] == "input keyevent 4"
        assert mock_adb.shell.call_args_list[1].args[0] == shell_join(
            ["input", "keyevent", "4;reboot"]
        )

    def test_tap_and_swipe_keep_numeric_commands(self):
        mock_adb = MagicMock(spec=AdbClient)
        native = NativeAdb(mock_adb)
        native.tap(10, 20)
        native.swipe(1, 2, 3, 4, 300)
        assert mock_adb.shell.call_args_list[0].args[0] == "input tap 10 20"
        assert mock_adb.shell.call_args_list[1].args[0] == "input swipe 1 2 3 4 300"


class TestTemporaryFiles:
    def test_dump_ui_reads_and_removes_temp_file(self, tmp_path, monkeypatch):
        created = {}

        def fake_temp(suffix):
            path = tmp_path / f"dump{suffix}"
            path.write_text("", encoding="utf-8")
            created["path"] = path
            return path

        monkeypatch.setattr("aidb_locator.commands._temporary_path", fake_temp)
        mock_adb = MagicMock(spec=AdbClient)

        def fake_pull(remote, local):
            Path(local).write_text("<hierarchy/>", encoding="utf-8")
            return Path(local)

        mock_adb.pull.side_effect = fake_pull
        xml = NativeAdb(mock_adb).dump_ui()

        assert xml == "<hierarchy/>"
        mock_adb.shell.assert_called_once_with("uiautomator dump /sdcard/aidb_uidump.xml")
        assert not created["path"].exists()

    def test_dump_ui_removes_temp_file_when_pull_fails(self, tmp_path, monkeypatch):
        created = {}

        def fake_temp(suffix):
            path = tmp_path / f"dump{suffix}"
            path.write_text("", encoding="utf-8")
            created["path"] = path
            return path

        monkeypatch.setattr("aidb_locator.commands._temporary_path", fake_temp)
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.pull.side_effect = AdbError("pull failed")

        try:
            NativeAdb(mock_adb).dump_ui()
            assert False, "Should have raised AdbError"
        except AdbError as e:
            assert "pull failed" in str(e)
        assert not created["path"].exists()

    def test_file_broadcast_result_removes_temp_file(self, tmp_path, monkeypatch):
        app_data = {
            "code": 0,
            "data": {
                "bd": "com.example.app",
                "b7": {"ag": "com.example.MainActivity", "cj": [], "ck": []},
                "bc": [],
            },
        }
        payload = base64.b64encode(zlib.compress(json.dumps(app_data).encode("utf-8"))).decode("ascii")
        created = {}

        def fake_temp(suffix):
            path = tmp_path / f"result{suffix}"
            path.write_bytes(b"")
            created["path"] = path
            return path

        monkeypatch.setattr("aidb_locator.commands._temporary_path", fake_temp)
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.broadcast.return_value = "FP:/sdcard/Download/codeLocator_data.txt"

        def fake_pull(remote, local):
            Path(local).write_text(payload, encoding="ascii")
            return Path(local)

        mock_adb.pull.side_effect = fake_pull
        result = CodeLocator(mock_adb).grab_layout()

        assert isinstance(result, WApplication)
        assert result.package_name == "com.example.app"
        assert not created["path"].exists()

    def test_screenshot_default_path_uses_secure_temp_file(self, monkeypatch):
        def reject_mktemp(*args, **kwargs):
            raise AssertionError("tempfile.mktemp is deprecated")

        monkeypatch.setattr(tempfile, "mktemp", reject_mktemp)
        mock_adb = MagicMock(spec=AdbClient)

        def fake_pull(remote, local):
            Path(local).write_bytes(b"png")
            return Path(local)

        mock_adb.pull.side_effect = fake_pull
        path = NativeAdb(mock_adb).screenshot()
        try:
            assert path.exists()
            assert path.suffix == ".png"
            assert path.parent == Path(tempfile.gettempdir())
            assert path.read_bytes() == b"png"
        finally:
            path.unlink(missing_ok=True)

    def test_screenshot_removes_owned_temp_when_capture_fails(self, tmp_path, monkeypatch):
        temp = tmp_path / "shot.png"
        temp.write_bytes(b"")
        monkeypatch.setattr("aidb_locator.commands._temporary_path", lambda suffix: temp)
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.shell.side_effect = AdbError("screencap failed")
        mock_adb.emulator_screenshot.side_effect = AdbError("not an emulator")

        try:
            NativeAdb(mock_adb).screenshot()
            assert False, "Should have raised AdbError"
        except AdbError as e:
            assert "screencap failed" in str(e)
        assert not temp.exists()

    def test_screenshot_keeps_caller_path_when_capture_fails(self, tmp_path):
        output = tmp_path / "keep.png"
        output.write_bytes(b"original")
        mock_adb = MagicMock(spec=AdbClient)
        mock_adb.shell.side_effect = AdbError("screencap failed")
        mock_adb.emulator_screenshot.side_effect = AdbError("not an emulator")

        try:
            NativeAdb(mock_adb).screenshot(output)
            assert False, "Should have raised AdbError"
        except AdbError as e:
            assert "screencap failed" in str(e)
        assert output.read_bytes() == b"original"
