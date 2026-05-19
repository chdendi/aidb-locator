from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

from aidb_locator.adb import AdbClient, AdbError, Device


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
