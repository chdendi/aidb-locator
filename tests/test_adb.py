from __future__ import annotations

import shlex
import subprocess
from unittest.mock import patch, MagicMock

from aidb_locator.adb import AdbClient, AdbError, Device, shell_join
from aidb_locator.protocol import ACTION_LAYOUT_INFO, build_broadcast_command


class TestAdbClientBuildCmd:
    def test_no_serial(self):
        client = AdbClient()
        cmd = client._build_cmd(["shell", "ls"])
        assert cmd == ["adb", "shell", "ls"]

    def test_with_serial(self):
        client = AdbClient(device_serial="abc123")
        cmd = client._build_cmd(["shell", "ls"])
        assert cmd == ["adb", "-s", "abc123", "shell", "ls"]


class TestAdbClientShell:
    @patch("aidb_locator.adb.subprocess.run")
    def test_shell_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="output\n", stderr=""
        )
        client = AdbClient()
        result = client.shell("ls /sdcard")
        assert result == "output\n"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["adb", "shell", "ls /sdcard"]

    @patch("aidb_locator.adb.subprocess.run")
    def test_shell_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="adb", timeout=10)
        client = AdbClient()
        try:
            client.shell("hang")
            assert False, "Should have raised AdbError"
        except AdbError as e:
            assert "timed out" in str(e).lower()


class TestListDevices:
    @patch("aidb_locator.adb.subprocess.run")
    def test_parse_devices(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="List of devices attached\nabc123\tdevice\ndef456\toffline\n\n",
            stderr="",
        )
        client = AdbClient()
        devices = client.list_devices()
        assert len(devices) == 2
        assert devices[0] == Device(serial="abc123", state="device")
        assert devices[1] == Device(serial="def456", state="offline")

    @patch("aidb_locator.adb.subprocess.run")
    def test_no_devices(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="List of devices attached\n\n",
            stderr="",
        )
        client = AdbClient()
        devices = client.list_devices()
        assert devices == []


class TestEmulatorScreenshot:
    @patch("aidb_locator.adb.subprocess.run")
    def test_emulator_screenshot(self, mock_run, tmp_path):
        output = tmp_path / "shot.png"

        def fake_run(cmd, **kwargs):
            output.write_bytes(b"\x89PNG\r\n\x1a\nDATA")
            return MagicMock(returncode=0, stdout="OK\n", stderr="")

        mock_run.side_effect = fake_run
        client = AdbClient()
        result = client.emulator_screenshot(output)

        assert result == output
        args = mock_run.call_args[0][0]
        assert args == ["adb", "emu", "screenrecord", "screenshot", str(output)]


class TestShellJoin:
    def test_leaves_codelocator_safe_tokens_unquoted(self):
        args = build_broadcast_command(
            ACTION_LAYOUT_INFO,
            {"name": "value with spaces and 'quotes'"},
        )
        joined = shell_join(args)
        # Base64 extras and action names sit in shlex's safe set, so the
        # command matches a plain join and stays compatible with CodeLocator.
        assert joined == " ".join(args)
        assert "'" not in joined
        assert joined.startswith(
            "am broadcast -a com.bytedance.tools.codelocator.action_debug_layout_info "
            "--es codeLocator_shell_args "
        )

    def test_quotes_spaces_quotes_and_metacharacters(self):
        assert shell_join(["input", "text", "hello%sworld"]) == "input text hello%sworld"
        assert shell_join(["echo", "it's"]) == "echo " + shlex.quote("it's")
        assert shell_join(["echo", "a b"]) == "echo 'a b'"
        assert shell_join(["echo", "a;rm"]) == "echo 'a;rm'"
        assert shell_join(["echo", "$(id)"]) == "echo '$(id)'"
        assert shell_join(["echo", ""]) == "echo ''"


class TestBroadcastQuoting:
    @patch("aidb_locator.adb.subprocess.run")
    def test_codelocator_broadcast_command_shape(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        args = {"k": "value with spaces and 'quotes'"}
        client = AdbClient()
        client.broadcast(ACTION_LAYOUT_INFO, args)

        cmd = mock_run.call_args[0][0]
        shell_args = build_broadcast_command(ACTION_LAYOUT_INFO, args)
        assert cmd[:2] == ["adb", "shell"]
        assert cmd[2] == shell_join(shell_args)
        assert cmd[2] == " ".join(shell_args)
        assert mock_run.call_args.kwargs["timeout"] == 30

    @patch("aidb_locator.adb.subprocess.run")
    def test_unsafe_action_is_quoted(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        client = AdbClient()
        client.broadcast("bad;rm -rf", None)
        shell = mock_run.call_args[0][0][2]
        assert shell == shell_join(["am", "broadcast", "-a", "bad;rm -rf"])
        assert "'bad;rm -rf'" in shell
