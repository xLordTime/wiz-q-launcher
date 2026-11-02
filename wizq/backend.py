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
    "backend": "Das native Deimos-Backend fehlt oder konnte nicht geladen werden.",
    "permission": "Windows verweigert den Zugriff auf den Spielclient. Spiel und Launcher mit denselben Berechtigungen starten.",
    "module": "Das Spielmodul wurde noch nicht vollständig geladen. Die Initialisierungswartezeit in den Einstellungen erhöhen.",
    "login_missing": "Das Loginmuster passt nicht zum installierten Spielclient. Launcher und Spielclient aktualisieren.",
    "login_ambiguous": "Das Loginmuster ist mehrdeutig. Es wurde kein Anmeldebefehl gesendet.",
    "hook_missing": "Das Fenstermuster passt nicht zum installierten Spielclient. Launcher und Spielclient aktualisieren.",
    "hook_ambiguous": "Das Fenstermuster ist mehrdeutig. Es wurde kein Anmeldebefehl gesendet.",
    "initializing": "Der Spielclient war innerhalb der Wartezeit noch nicht bereit. Die Initialisierungswartezeit erhöhen.",
    "memory": "Der Spielspeicher konnte nicht gelesen oder beschrieben werden. Spielclient und Berechtigungen prüfen.",
    "hook_timeout": "Der Spielclient hat den Anmeldebefehl nicht rechtzeitig verarbeitet. Die Anmeldung wird nicht automatisch wiederholt.",
    "worker_timeout": "Der Autologin-Hilfsprozess hat sein Zeitlimit überschritten.",
    "worker_crash": "Der native Autologin-Hilfsprozess wurde unerwartet beendet.",
    "unsupported": "Der installierte Client wird vom Autologin-Adapter aktuell nicht unterstützt.",
}
RETRYABLE_LOGIN_ERRORS = {"module", "login_missing", "hook_missing", "initializing"}


def login_error_code(error):
    text = str(error)
    for marker, code in (
        ("LOGIN_PATTERN ambiguous", "login_ambiguous"),
        ("LOGIN_PATTERN not found", "login_missing"),
        ("HOOK_PATTERN ambiguous", "hook_ambiguous"),
        ("HOOK_PATTERN not found", "hook_missing"),
        ("CLIENT_NOT_READY", "initializing"),
        ("OpenProcess:", "permission"),
        ("CreateToolhelp32Snapshot:", "module"),
        ("Module 'WizardGraphicalClient.exe' not found", "module"),
        ("Timed out waiting for login bytecode", "hook_timeout"),
        ("ReadProcessMemory", "memory"),
        ("WriteProcessMemory", "memory"),
    ):
        if marker in text:
            return code
    return "unsupported"


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
    if account and native is None:
        raise RuntimeError(
            "Das native Deimos-Backend fehlt. Windows-Build verwenden oder ohne Autologin starten."
        )
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
        finally:
            del credentials, payload
            # The worker's finally cannot run if Windows terminates it or the
            # parent kills it after a timeout. Always restore the exact window.
            try:
                if alive(pid, created) and (hwnd, pid) in window_handles():
                    user_function("EnableWindow", [ctypes.c_void_p, ctypes.c_int])(hwnd, 1)
            except OSError:
                pass
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
    """Process isolation for a native backend fault, not a security sandbox."""
    hwnd, pid, created = None, None, None
    disabled = False

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
        native = native_module()
        if native is None:
            return fail("backend", 3)
        ready_timeout = max(2, min(60, int(payload.get("ready_timeout", 15))))
        deadline = time.monotonic() + ready_timeout
        # Match Deimos: prevent input during dispatch and let the window initialize.
        user_function("EnableWindow", [ctypes.c_void_p, ctypes.c_int])(hwnd, 0)
        disabled = True
        time.sleep(2)
        while valid():
            try:
                native.login(hwnd, payload["username"], payload["password"])
                return 0
            except Exception as exc:
                code = login_error_code(exc)
                # These failures occur before allocations or any dispatch. Never
                # retry a timeout, write failure, ambiguous pattern or sent login.
                if code not in RETRYABLE_LOGIN_ERRORS or time.monotonic() >= deadline:
                    return fail(code)
                time.sleep(0.5)
        return fail("identity", 2)
    except Exception:
        return fail("unsupported")
    finally:
        if disabled:
            try:
                if valid():
                    user_function("EnableWindow", [ctypes.c_void_p, ctypes.c_int])(hwnd, 1)
            except Exception:
                pass
