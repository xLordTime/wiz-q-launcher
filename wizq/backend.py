"""Windows launch adapter. Credentials never appear in a command line."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .settings import REGIONS, get

PROCESS_NAME = "wizardgraphicalclient.exe"


def native_module():
    try:
        import wizq_native

        return wizq_native
    except ImportError:
        return None


def window_handles():
    if sys.platform != "win32":
        return []
    native = native_module()
    if native:
        return native.windows()
    from ctypes import wintypes

    u = ctypes.windll.user32
    u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = []

    @callback
    def visit(hwnd, _):
        name = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, name, 256)
        if name.value == "Wizard Graphical Client":
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((int(hwnd), pid.value))
        return True

    u.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    u.EnumWindows(visit, 0)
    return found


def alive(pid, created):
    try:
        p = psutil.Process(pid)
        return p.is_running() and abs(p.create_time() - created) < 0.01 and p.name().lower() == PROCESS_NAME
    except (psutil.Error, OSError):
        return False


def instances():
    result = []
    for hwnd, pid in window_handles():
        try:
            p = psutil.Process(pid)
            if p.name().lower() == PROCESS_NAME:
                result.append({"hwnd": hwnd, "pid": pid, "created": p.create_time()})
        except psutil.Error:
            continue
    return result


def user_function(name, argtypes, restype=ctypes.c_int):
    if sys.platform != "win32":
        raise RuntimeError("Diese Funktion benötigt Windows.")
    function = getattr(ctypes.windll.user32, name)
    function.argtypes, function.restype = argtypes, restype
    return function


def focus(hwnd):
    user_function("ShowWindow", [ctypes.c_void_p, ctypes.c_int])(hwnd, 9)
    user_function("SetForegroundWindow", [ctypes.c_void_p])(hwnd)


def set_title(hwnd, nickname):
    user_function("SetWindowTextW", [ctypes.c_void_p, ctypes.c_wchar_p])(hwnd, nickname)


def placement(hwnd, rect, borderless=False):
    getter = user_function("GetWindowLongPtrW", [ctypes.c_void_p, ctypes.c_int], ctypes.c_ssize_t)
    setter = user_function(
        "SetWindowLongPtrW", [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t
    )
    style = getter(hwnd, -16)
    mask = 0x00C00000 | 0x00040000
    setter(hwnd, -16, style & ~mask if borderless else style | mask)
    x, y, w, h = map(int, rect)
    user_function(
        "SetWindowPos",
        [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ],
    )(hwnd, None, x, y, w, h, 0x0004 | 0x0020 | 0x0040)


def window_rect(hwnd):
    from ctypes import wintypes

    rect = wintypes.RECT()
    user_function("GetWindowRect", [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)])(hwnd, ctypes.byref(rect))
    return [rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top]


def detect_installs():
    found = {}
    roots = [
        Path(r"C:\ProgramData\KingsIsle Entertainment"),
        Path(r"C:\Program Files (x86)\KingsIsle Entertainment"),
        Path(r"C:\Program Files\KingsIsle Entertainment"),
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for folder in root.glob("Wizard101*"):
            if not (folder / "Bin/WizardGraphicalClient.exe").is_file():
                continue
            suffix = folder.name.rsplit("(", 1)[-1].rstrip(")").lower()
            region = suffix if suffix in REGIONS else "us"
            found.setdefault(region, str(folder))
    return found


def launch(store, vault, region, account=None):
    if sys.platform != "win32":
        raise RuntimeError("Der Spielstart ist nur unter Windows möglich.")
    path = Path(get(store, "region_install_" + region))
    exe = path / "Bin/WizardGraphicalClient.exe"
    if not exe.is_file():
        raise ValueError(
            f"Spielordner für {region.upper()} fehlt. Einstellungen → Launcher & Regionen öffnen."
        )
    server, port = get(store, "region_server_" + region), get(store, "region_port_" + region)
    native = native_module()
    if account and native is None:
        raise RuntimeError(
            "Das native Deimos-Backend fehlt. Windows-Build verwenden oder ohne Autologin starten."
        )
    if native:
        pid = native.launch(str(path), f"{server}:{port}", region)
    else:
        args = [str(exe), "-L", server, str(port)]
        if region != "us":
            args += ["-A", region]
        pid = subprocess.Popen(args, cwd=exe.parent).pid
    created = psutil.Process(pid).create_time()
    deadline, hwnd = time.monotonic() + get(store, "login_timeout"), None
    while time.monotonic() < deadline:
        if not alive(pid, created):
            raise RuntimeError("Der gestartete Client wurde vor dem Login beendet.")
        hwnd = next((h for h, p in window_handles() if p == pid), None)
        if hwnd:
            break
        time.sleep(0.2)
    if not hwnd:
        raise RuntimeError(
            "Client gestartet, aber sein Fenster wurde nicht rechtzeitig gefunden. Kein anderer Client wurde verwendet."
        )
    warning = None
    if account:
        credentials = store.credentials(vault, account["id"])
        payload = {"hwnd": hwnd, "pid": pid, "created": created, **credentials}
        command = (
            [sys.executable, "--login-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"), "--login-worker"]
        )
        time.sleep(2)
        if not alive(pid, created):
            raise RuntimeError("Der Client wurde vor der Anmeldung beendet.")
        try:
            result = subprocess.run(
                command,
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=25,
                creationflags=0x08000000,
            )
            if result.returncode:
                warning = "Autologin nicht ausgeführt (Clientmuster/Backend). Das Fenster bleibt für manuelle Anmeldung offen."
        except subprocess.TimeoutExpired:
            warning = "Autologin-Timeout. Das Fenster bleibt offen; Anmeldung prüfen."
        finally:
            del credentials, payload
        if get(store, "set_window_title"):
            set_title(hwnd, account["nickname"])
    return {
        "pid": pid,
        "created": created,
        "hwnd": hwnd,
        "region": region,
        "account_id": account["id"] if account else None,
        "warning": warning,
    }


def login_worker():
    """Process isolation for a native backend fault, not a security sandbox."""
    try:
        payload = json.loads(sys.stdin.buffer.read(65536))
        if not alive(int(payload["pid"]), float(payload["created"])):
            return 2
        if (int(payload["hwnd"]), int(payload["pid"])) not in window_handles():
            return 2
        native = native_module()
        if native is None:
            return 3
        native.login(int(payload["hwnd"]), payload["username"], payload["password"])
        return 0
    except Exception:
        # Native error strings are not returned to logs or the parent process.
        return 4
