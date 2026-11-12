"""Windows launch adapter. Credentials never appear in a command line."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .settings import GAME_LANGUAGES, REGIONS, game_language, get

PROCESS_NAME = "wizardgraphicalclient.exe"

# Only these fixed codes cross the worker boundary. Native exception strings
# can contain arbitrary text and are never displayed, persisted or forwarded.
LOGIN_ERRORS = {
    "identity": "Der gestartete Client ist nicht mehr verfügbar oder sein Fenster gehört nicht mehr zu diesem Prozess.",
    "input_failed": "Die Eingabe im Anmeldefenster wurde unterbrochen. Prüfe die Initialisierungswartezeit und ob Spiel und Launcher mit denselben Windows-Berechtigungen laufen.",
    "credentials": "Die Zugangsdaten enthalten ein Steuerzeichen, das sich nicht als Text eingeben lässt.",
    "worker_timeout": "Der Autologin-Hilfsprozess hat sein Zeitlimit überschritten.",
    "worker_crash": "Der Autologin-Hilfsprozess wurde unerwartet beendet.",
}


def launch_arguments(server, port, language):
    if language not in GAME_LANGUAGES:
        raise ValueError("Unbekannte Spielsprache")
    args = ["-L", server, str(port)]
    if language != "us":
        args += ["-A", language]
    return args


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
    from .win32_windows import Win32Windows

    Win32Windows().apply(hwnd, rect, "borderless" if borderless else "unchanged")


def window_rect(hwnd):
    from .win32_windows import Win32Windows

    return Win32Windows().rect(hwnd)


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


def launch(store, vault, region, account=None, language=None):
    if sys.platform != "win32":
        raise RuntimeError("Der Spielstart ist nur unter Windows möglich.")
    language = game_language(store, region, language)
    path = Path(get(store, "region_install_" + region))
    exe = path / "Bin/WizardGraphicalClient.exe"
    if not exe.is_file():
        raise ValueError(
            f"Spielordner für {region.upper()} fehlt. Einstellungen → Launcher & Regionen öffnen."
        )
    server, port = get(store, "region_server_" + region), get(store, "region_port_" + region)
    native = native_module()
    if native:
        pid = native.launch(str(path), f"{server}:{port}", language)
    else:
        args = [str(exe), *launch_arguments(server, port, language)]
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
        ready_timeout = get(store, "login_ready_timeout")
        payload = {
            "hwnd": hwnd,
            "pid": pid,
            "created": created,
            "ready_timeout": ready_timeout,
            **credentials,
        }
        command = (
            [sys.executable, "--login-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"), "--login-worker"]
        )
        if not alive(pid, created):
            raise RuntimeError("Der Client wurde vor der Anmeldung beendet.")
        try:
            result = subprocess.run(
                command,
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=ready_timeout + 20,
                creationflags=0x08000000,
                encoding="utf-8",
            )
            if result.returncode:
                code = "worker_crash"
                try:
                    reply = json.loads(result.stdout[:4096])
                    if isinstance(reply, dict) and reply.get("code") in LOGIN_ERRORS:
                        code = reply["code"]
                except (ValueError, TypeError):
                    pass
                warning = f"Autologin [{code}]: {LOGIN_ERRORS[code]} Das Fenster bleibt für die manuelle Anmeldung offen."
        except subprocess.TimeoutExpired:
            warning = f"Autologin [worker_timeout]: {LOGIN_ERRORS['worker_timeout']} Das Fenster bleibt offen; Anmeldung prüfen."
        except OSError:
            warning = f"Autologin [worker_crash]: {LOGIN_ERRORS['worker_crash']} Das Fenster bleibt für die manuelle Anmeldung offen."
        finally:
            del credentials, payload
        if get(store, "set_window_title"):
            set_title(hwnd, account["nickname"])
    return {
        "pid": pid,
        "created": created,
        "hwnd": hwnd,
        "region": region,
        "language": language,
        "account_id": account["id"] if account else None,
        "warning": warning,
    }


def login_worker():
    """Enter credentials into the verified login window without stealing focus."""
    hwnd, pid, created = None, None, None

    def fail(code, result=4):
        print(json.dumps({"code": code}), flush=True)
        return result

    def valid():
        return alive(pid, created) and (hwnd, pid) in window_handles()

    try:
        payload = json.loads(sys.stdin.buffer.read(65536))
        hwnd, pid, created = int(payload["hwnd"]), int(payload["pid"]), float(payload["created"])
        if not valid():
            return fail("identity", 2)
        username, password = payload["username"], payload["password"]
        if any(ord(char) < 32 or ord(char) == 127 for field in (username, password) for char in field):
            return fail("credentials")
        ready_timeout = max(2, min(60, int(payload.get("ready_timeout", 15))))
        time.sleep(ready_timeout)
        if not valid():
            return fail("identity", 2)

        send_message = user_function(
            "SendMessageTimeoutW",
            [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
             ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)],
            ctypes.c_ssize_t,
        )
        get_window_pid = user_function(
            "GetWindowThreadProcessId",
            [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)],
            ctypes.c_uint32,
        )
        window_enabled = user_function("IsWindowEnabled", [ctypes.c_void_p])
        scan_code = user_function("MapVirtualKeyW", [ctypes.c_uint, ctypes.c_uint], ctypes.c_uint)
        owner = ctypes.c_uint32()
        result = ctypes.c_size_t()
        fields = ((username.encode("utf-16-le"), 0x09), (password.encode("utf-16-le"), 0x0D))
        for text, virtual_key in fields:
            # The client accepts WM_CHAR for text but handles Tab and Enter as keys.
            events = [
                (0x0102, int.from_bytes(text[offset:offset + 2], "little"), 1)
                for offset in range(0, len(text), 2)
            ]
            key_details = 1 | (scan_code(virtual_key, 0) << 16)
            events.extend((
                (0x0100, virtual_key, key_details),  # WM_KEYDOWN
                (0x0101, virtual_key, key_details | 0xC0000000),  # WM_KEYUP
            ))
            for message, key, details in events:
                if not get_window_pid(hwnd, ctypes.byref(owner)) or owner.value != pid or not alive(pid, created):
                    return fail("identity", 2)
                # SMTO_BLOCK | SMTO_ABORTIFHUNG | SMTO_ERRORONEXIT.
                if not window_enabled(hwnd) or not send_message(
                    hwnd, message, key, details, 0x23, 1000, ctypes.byref(result)
                ):
                    return fail("input_failed")
            if virtual_key == 0x09:
                # Allow the client to process the field change before typing the password.
                time.sleep(0.25)
        return 0
    except Exception:
        return fail("worker_crash")
