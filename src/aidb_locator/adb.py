"""ADB client — subprocess wrapper for adb commands."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


def shell_join(args: list[object]) -> str:
    """Quote and join arguments for a remote ``adb shell`` command.

    ``shlex.quote`` keeps spaces, single quotes, and shell metacharacters
    from breaking the remote shell or injecting extra commands. Tokens in
    the POSIX safe set — including CodeLocator's Base64 broadcast extras —
    stay unquoted, so those commands keep their existing shape.
    """
    return " ".join(shlex.quote(str(arg)) for arg in args)


class AdbError(Exception):
    """Raised when an ADB command fails."""


@dataclass(frozen=True)
class Device:
    serial: str
    state: str


class AdbClient:
    def __init__(self, device_serial: str | None = None, timeout: int = 10):
        self._serial = device_serial
        self._timeout = timeout

    def _build_cmd(self, args: list[str]) -> list[str]:
        cmd = ["adb"]
        if self._serial:
            cmd.extend(["-s", self._serial])
        cmd.extend(args)
        return cmd

    def _run(self, args: list[str], timeout: int | None = None) -> str:
        cmd = self._build_cmd(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self._timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"ADB command timed out after {self._timeout}s: {cmd}") from e
        except FileNotFoundError as e:
            raise AdbError(
                "adb not found. Make sure Android SDK platform-tools is in your PATH."
            ) from e

        if result.returncode != 0 and result.stderr.strip():
            raise AdbError(f"ADB error: {result.stderr.strip()}")
        return result.stdout

    def shell(self, command: str) -> str:
        """Run an adb shell command and return stdout."""
        return self._run(["shell", command])

    def broadcast(self, action: str, args: dict[str, str] | None = None) -> str:
        """Send a broadcast via adb shell am broadcast."""
        from aidb_locator.protocol import build_broadcast_command

        shell_args = build_broadcast_command(action, args)
        return self._run(["shell", shell_join(shell_args)], timeout=30)

    def pull(self, remote_path: str, local_path: str | Path) -> Path:
        """Pull a file from device to local path."""
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        self._run(["pull", remote_path, str(local)])
        if not local.exists():
            raise AdbError(f"Pull succeeded but file not found: {local}")
        return local

    def emulator_screenshot(self, local_path: str | Path) -> Path:
        """Take a host-side emulator screenshot."""
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        self._run(["emu", "screenrecord", "screenshot", str(local)])
        if not local.exists():
            raise AdbError(f"Emulator screenshot succeeded but file not found: {local}")
        return local

    def list_devices(self) -> list[Device]:
        """List connected ADB devices."""
        output = self._run(["devices"])
        devices = []
        for line in output.strip().splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) == 2:
                devices.append(Device(serial=parts[0], state=parts[1]))
        return devices
