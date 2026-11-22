"""Windows launch adapter. Credentials never appear in a command line."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .game_install import CLIENT, PATCHER, install_folder, is_steam_install
from .launch_methods import LAUNCH_METHOD_PATH_PREFIX, client_path, launch_method
from .settings import GAME_LANGUAGES, game_language, get, login_endpoint

PROCESS_NAME = CLIENT.name.casefold()
GAME_FOLDERS = "Einstellungen → Launcher & Regionen"
GAME_UPDATE = GAME_FOLDERS + " → Spiel aktualisieren"

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


def selected_game_folder(store, region, *, allow_steam_library=False):
    try:
        folder = install_folder(get(store, "region_install_" + region))
    except ValueError as exc:
        raise ValueError(f"{region.upper()} · {exc} Öffne {GAME_FOLDERS}.") from None
    if is_steam_install(folder) and not allow_steam_library:
        raise ValueError(
            "Dieser Spielordner liegt in einer Steam-Bibliothek. Nutze Steam-Direktstart für diesen Ordner. "
            "Für den normalen Direktstart und den Patch-Assistenten wähle den Ordner der eigenständigen Installation."
        )
    return folder


def open_game_patcher(store, region):
    if sys.platform != "win32":
        raise RuntimeError("Der Wizard101-Assistent benötigt Windows.")
    patcher = selected_game_folder(store, region) / PATCHER
    try:
        if not patcher.is_file():
            raise ValueError(f"Wizard101-Assistent fehlt unter {patcher}. Prüfe den Spielordner für {region.upper()}.")
        os.startfile(str(patcher), cwd=str(patcher.parent))
    except OSError as exc:
        raise RuntimeError(f"Wizard101-Assistent konnte nicht geöffnet werden · {patcher}. {exc}") from None
    return patcher


def launch(store, vault, region, account=None, language=None, *, steam=False):
    if sys.platform != "win32":
        raise RuntimeError("Der Spielstart ist nur unter Windows möglich.")
    method_id = account.get("launch_method_id") if account else None
    with store.lock:
        method = launch_method(store, method_id) if method_id else None
        if method_id and method is None:
            raise ValueError(f"{account['nickname']} · Die Startmethode fehlt. Wähle sie in den Account-Eigenschaften neu.")
        if method:
            region, steam = method.region, method.steam
            custom_path = store.get(LAUNCH_METHOD_PATH_PREFIX + method.id, "")
        else:
            steam = steam or bool(account and account.get("steam"))
        language = game_language(store, region, language)
        server, port = login_endpoint(store, region, steam=steam)
    if method:
        caption = f"Startmethode „{method.name}“"
        location = f"{GAME_FOLDERS} → Startmethoden verwalten"
        if not custom_path:
            raise ValueError(f"{caption} · Wähle unter {location} die Clientdatei für diesen PC.")
        exe = client_path(custom_path)
        if is_steam_install(exe.parent) and not steam:
            raise ValueError(f"{caption} · Wähle für diese Steam-Installation den Modus Steam-Direktstart.")
        path = None
        missing = f"{caption} · Client fehlt unter {exe}. Prüfe den Pfad unter {location}."
        patch_help = "Aktualisiere bei einem veralteten Client die gewählte Installation."
    else:
        path = selected_game_folder(store, region, allow_steam_library=steam)
        exe = path / CLIENT
        missing = (
            f"{region.upper()} · Client fehlt unter {exe}. Prüfe den Pfad unter {GAME_FOLDERS} "
            "oder öffne dort den Patch-Assistenten über Spiel aktualisieren."
        )
        patch_help = f"Bei einem veralteten Client öffne {GAME_UPDATE}."
    try:
        if not exe.is_file():
            raise ValueError(missing)
        native = native_module() if path else None
        if native:
            pid = native.launch(str(path), f"{server}:{port}", language)
        else:
            args = [str(exe), *launch_arguments(server, port, language)]
            pid = subprocess.Popen(args, cwd=exe.parent).pid
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(f"Client konnte nicht gestartet werden · {exe}. {exc}") from None
    exited = f"Client vor dem Login beendet · {exe}. {patch_help}"
    try:
        created = psutil.Process(pid).create_time()
    except psutil.NoSuchProcess:
        raise RuntimeError(exited) from None
    deadline, hwnd = time.monotonic() + get(store, "login_timeout"), None
    while time.monotonic() < deadline:
        if not alive(pid, created):
            raise RuntimeError(exited)
        hwnd = next((h for h, p in window_handles() if p == pid), None)
        if hwnd:
            break
        time.sleep(0.2)
    if not hwnd:
        raise RuntimeError(
            f"Fenster des gestarteten Clients wurde nicht rechtzeitig gefunden · {exe}."
        )
    warning = None
    if account and not steam:
        credentials = store.credentials(vault, account["id"])
        if credentials["username"].strip() and credentials["password"]:
            if not alive(pid, created):
                raise RuntimeError(exited)
            warning = run_autologin(
                hwnd, pid, created, get(store, "login_ready_timeout"), credentials
            )
        else:
            warning = (
                "Autologin · Ergänze die Zugangsdaten in den Account-Eigenschaften. "
                "Das Fenster bleibt für die manuelle Anmeldung offen."
            )
        del credentials
    if account and get(store, "set_window_title"):
        set_title(hwnd, account["nickname"])
    return {
        "pid": pid,
        "created": created,
        "hwnd": hwnd,
        "exe": str(exe),
        "region": region,
        "language": language,
        "steam": steam,
        "launch_method_name": method.name if method else None,
        "login_endpoint": f"{server}:{port}",
        "account_id": account["id"] if account else None,
        "warning": warning,
    }


def run_autologin(hwnd, pid, created, ready_timeout, credentials):
    payload = {"hwnd": hwnd, "pid": pid, "created": created, "ready_timeout": ready_timeout, **credentials}
    command = (
        [sys.executable, "--login-worker"]
        if getattr(sys, "frozen", False)
        else [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"), "--login-worker"]
    )
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
        if not result.returncode:
            return None
        reply = json.loads(result.stdout[:4096])
        code = reply.get("code") if isinstance(reply, dict) else None
        if code not in LOGIN_ERRORS:
            code = "worker_crash"
    except subprocess.TimeoutExpired:
        code = "worker_timeout"
    except (OSError, ValueError, TypeError):
        code = "worker_crash"
    return f"Autologin [{code}]: {LOGIN_ERRORS[code]} Das Fenster bleibt für die manuelle Anmeldung offen."


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
