"""Talking to the Android device that runs your bot's games.

RoyaleBot uses adb to forward the game link's port to this PC and to check the device. It
runs its own adb server (port 5039 by default), so other tools on the default server are
never disturbed. Every call names one device serial.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .policy import Refused

#: RoyaleBot talks to devices through its own adb server, so it never disturbs other tools
#: that use the default server on 5037.
DEFAULT_ADB_PORT = 5039


class AdbMissing(RuntimeError):
    pass


def _devices(adb: Path, port: int) -> list[str]:
    """Serials adb reports as ready, on RoyaleBot's own server."""
    out = subprocess.run([str(adb), "-P", str(port), "devices"], capture_output=True, text=True, timeout=30).stdout
    ready = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device":
            ready.append(parts[0])
    return ready


def find_adb() -> Path:
    """Locate adb: ROYALEBOT_ADB, then the Android SDK, then PATH."""
    override = os.environ.get("ROYALEBOT_ADB")
    if override:
        if Path(override).is_file():
            return Path(override)
        raise AdbMissing(f"ROYALEBOT_ADB points at {override}, which is not a file.")
    exe = "adb.exe" if os.name == "nt" else "adb"
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(var)
        if root:
            candidate = Path(root) / "platform-tools" / exe
            if candidate.is_file():
                return candidate
    found = shutil.which("adb")
    if found:
        return Path(found)
    raise AdbMissing("adb not found. Install Android platform-tools and set ANDROID_HOME, or set ROYALEBOT_ADB.")


@dataclass(frozen=True)
class Device:
    adb: Path
    serial: str
    server_port: int = DEFAULT_ADB_PORT

    @classmethod
    def from_env(cls, serial: str | None = None) -> "Device":
        adb = find_adb()
        port = int(os.environ.get("ROYALEBOT_ADB_PORT", DEFAULT_ADB_PORT))
        serial = serial or os.environ.get("ROYALEBOT_SERIAL")
        if not serial:
            attached = _devices(adb, port)
            if len(attached) == 1:
                serial = attached[0]
            elif not attached:
                raise Refused("No device found. Plug one in or start your emulator (`adb devices` should list it).")
            else:
                raise Refused(f"More than one device: pass --serial (one of {', '.join(attached)}).")
        return cls(adb, serial, port)

    def _base(self) -> list[str]:
        return [str(self.adb), "-P", str(self.server_port), "-s", self.serial]

    def run(self, *args: str, check: bool = True, timeout: float = 120) -> str:
        result = subprocess.run(self._base() + list(args), capture_output=True, text=True, timeout=timeout)
        if check and result.returncode != 0:
            raise RuntimeError(f"adb {' '.join(args)} failed: {result.stdout}{result.stderr}")
        return result.stdout

    def connect(self) -> str:
        """Attach a network device (emulators) to RoyaleBot's own adb server."""
        result = subprocess.run(
            [str(self.adb), "-P", str(self.server_port), "connect", self.serial], capture_output=True, text=True, timeout=60
        )
        return result.stdout + result.stderr

    def shell(self, command: str, **kw) -> str:
        return self.run("shell", command, **kw)

    def getprop(self, name: str) -> str:
        return self.shell(f"getprop {name}").strip()

    def forward(self, local_port: int, device_port: int) -> None:
        self.run("forward", f"tcp:{local_port}", f"tcp:{device_port}")

    def remove_forward(self, local_port: int) -> None:
        self.run("forward", "--remove", f"tcp:{local_port}", check=False)
