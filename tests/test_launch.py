import ctypes
import io
import json
import os
import subprocess
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from wizq import backend, game_install
from wizq.launch_methods import save_launch_method
from wizq.settings import GAME_LANGUAGES, REGIONS, game_language, get, set_value


@pytest.mark.parametrize("region", REGIONS)
def test_game_language_is_independent_of_region_and_launcher_ui(profile, region):
    _, store, _ = profile
    assert game_language(store, region) == region
    store.set("language", "de")
    for language in GAME_LANGUAGES:
        set_value(store, "region_language_" + region, language)
        assert game_language(store, region) == language
        args = backend.launch_arguments(get(store, "region_server_" + region), 12000, language)
        assert args[:3] == ["-L", get(store, "region_server_" + region), "12000"]
        assert args[3:] == ([] if language == "us" else ["-A", language])
    assert game_language(store, region, "us") == "us"
    assert get(store, "region_language_" + region) == "gr"  # A one-off override is not persisted.
    with pytest.raises(ValueError):
        game_language(store, region, "arbitrary -L host")


def test_exact_german_server_examples(profile):
    _, store, _ = profile
    host = get(store, "region_server_de")
    assert backend.launch_arguments(host, 12000, "us") == ["-L", "login-de.eu.wizard101.com", "12000"]
    assert backend.launch_arguments(host, 12000, "de") == [
        "-L",
        "login-de.eu.wizard101.com",
        "12000",
        "-A",
        "de",
    ]


@pytest.mark.parametrize("native", [True, False])
def test_steam_account_starts_client_on_configured_server_without_credentials(
    launch_environment, monkeypatch, tmp_path, native
):
    store, vault, install = launch_environment
    if not native:
        install = tmp_path / "Steam library" / "steamapps" / "common" / "Wizard101"
        (install / "Bin").mkdir(parents=True)
        (install / game_install.CLIENT).touch()
        store.set("region_install_de", str(install))
    ident = store.save_account(vault, "Steam Wizard", "", "", "de", steam=True)
    (account,) = store.accounts()
    assert account["id"] == ident and account["steam"]
    set_value(store, "region_port_de", 12001)
    vault.lock()
    calls = []
    module = SimpleNamespace(launch=lambda *args: calls.append(args) or 42) if native else None
    monkeypatch.setattr(backend, "native_module", lambda: module)
    monkeypatch.setattr(
        backend.subprocess,
        "Popen",
        lambda args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(pid=42),
    )
    monkeypatch.setattr(backend, "set_title", lambda *args: None)
    monkeypatch.setattr(backend.os, "startfile", lambda *_: pytest.fail("No Steam application expected"), raising=False)
    monkeypatch.setattr(backend.subprocess, "run", lambda *_: pytest.fail("No login worker expected"))
    monkeypatch.setattr(store, "credentials", lambda *_: pytest.fail("No credential access expected"))
    result = backend.launch(store, vault, "de", account, "de")
    assert result["account_id"] == ident and result["steam"]
    assert result["login_endpoint"] == "login-en.eu.wizard101.com:12000"
    if native:
        assert calls == [(str(install), "login-en.eu.wizard101.com:12000", "de")]
    else:
        assert calls == [(
            [str(install / game_install.CLIENT), "-L", "login-en.eu.wizard101.com", "12000", "-A", "de"],
            {"cwd": install / "Bin"},
        )]


def test_empty_steam_and_standard_launch_use_independent_server_addresses(launch_environment, monkeypatch):
    store, vault, install = launch_environment
    calls = []
    monkeypatch.setattr(backend, "native_module", lambda: SimpleNamespace(launch=lambda *a: calls.append(a) or 42))
    key = "region_steam_address_de"
    with pytest.raises(ValueError, match="Hostnamen"):
        set_value(store, key, "login.example.test:70000")
    set_value(store, key, "login.example.test:12345")
    result = backend.launch(store, vault, "de", language="us", steam=True)
    assert result["account_id"] is None and result["steam"]
    assert result["login_endpoint"] == "login.example.test:12345"
    standard = backend.launch(store, vault, "de", language="us")
    assert not standard["steam"]
    assert calls == [
        (str(install), "login.example.test:12345", "us"),
        (str(install), "login-de.eu.wizard101.com:12000", "us"),
    ]
    assert get(store, "region_steam_address_us") == "login.us.wizard101.com:12000"


def test_direct_launch_identifies_a_steam_library_before_starting(launch_environment, monkeypatch, tmp_path):
    store, vault, _ = launch_environment
    install = tmp_path / "Custom library" / "steamapps" / "common" / "Wizard101"
    (install / "Bin").mkdir(parents=True)
    (install / "Bin" / "WizardGraphicalClient.exe").touch()
    store.set("region_install_de", str(install))
    monkeypatch.setattr(backend, "native_module", lambda: pytest.fail("No direct launch expected"))
    with pytest.raises(ValueError, match="Steam-Direktstart"):
        backend.launch(store, vault, "de")


@pytest.mark.parametrize(
    ("region", "steam", "host"),
    [
        ("de", True, "login-en.eu.wizard101.com"),
        ("de", False, "login-de.eu.wizard101.com"),
        ("us", True, "login.us.wizard101.com"),
        ("us", False, "login.us.wizard101.com"),
    ],
)
def test_custom_method_uses_exact_client_and_server_profile(launch_environment, monkeypatch, tmp_path, region, steam, host):
    store, vault, _ = launch_environment
    client = tmp_path / "Other drive with spaces" / game_install.CLIENT.name
    client.parent.mkdir()
    client.touch()
    method_id = save_launch_method(store, "Eigene Installation", region, steam, str(client))
    other_region = "us" if region == "de" else "de"
    ident = store.save_account(
        vault, "Wizard", "user", "password", other_region, launch_method_id=method_id
    )
    (account,) = store.accounts()
    assert account["region"] == region and account["default_region"] == other_region
    starts, autologins = [], []
    monkeypatch.setattr(backend, "native_module", lambda: pytest.fail("Native launcher uses the standard path"))
    monkeypatch.setattr(backend, "set_title", lambda *_: None)
    monkeypatch.setattr(
        backend.subprocess, "Popen", lambda args, **options: starts.append((args, options)) or SimpleNamespace(pid=42)
    )
    monkeypatch.setattr(
        backend, "run_autologin", lambda *args: autologins.append(args) or None
    )
    if steam:
        vault.lock()
    result = backend.launch(store, vault, other_region, account)
    args = [str(client), "-L", host, "12000"]
    if region == "de":
        args += ["-A", "de"]
    assert starts == [(args, {"cwd": client.parent})]
    assert result["account_id"] == ident and result["region"] == region
    assert result["launch_method_name"] == "Eigene Installation"
    assert result["login_endpoint"] == f"{host}:12000"
    assert bool(autologins) == (not steam)


@pytest.mark.parametrize("configured", [False, True])
def test_custom_method_never_falls_back_to_another_installation(launch_environment, monkeypatch, tmp_path, configured):
    store, vault, _ = launch_environment
    missing = str(tmp_path / "Missing" / game_install.CLIENT.name)
    method_id = save_launch_method(store, "A-Laufwerk", "de", False, missing if configured else "")
    store.save_account(vault, "Wizard", "user", "password", "de", launch_method_id=method_id)
    (account,) = store.accounts()
    monkeypatch.setattr(backend, "native_module", lambda: pytest.fail("No standard launch expected"))
    monkeypatch.setattr(backend.subprocess, "Popen", lambda *_: pytest.fail("No client start expected"))
    with pytest.raises(ValueError, match="A-Laufwerk.*(" + ("Client fehlt" if configured else "Clientdatei") + ")"):
        backend.launch(store, vault, "de", account)


@pytest.mark.parametrize("suffix", ("", r"\Bin", r"\Bin\WizardGraphicalClient.exe"))
def test_install_path_keeps_a_drive_and_accepts_bin_or_client(monkeypatch, suffix):
    monkeypatch.setattr(game_install, "Path", PureWindowsPath)
    folder = r"A:\Spiele mit Leerzeichen\Wizard101(DE)"
    assert game_install.install_folder(f'"{folder}{suffix}"') == PureWindowsPath(folder)
    with pytest.raises(ValueError, match="vollständigen Spielpfad"):
        game_install.install_folder(r"A:Wizard101(DE)")


def test_install_detection_keeps_both_copies_and_finds_registered_custom_path(monkeypatch, tmp_path):
    other_drive, system_drive = (tmp_path / letter for letter in ("A", "C"))
    current = other_drive / "Spiele" / "Wizard101(DE)"
    old = system_drive / "ProgramData" / "KingsIsle Entertainment" / "Wizard101(DE)"
    steam = other_drive / "Library" / "steamapps" / "common" / "Wizard101"
    registered = other_drive / "Benutzerdefiniert" / "MMOs" / "Anderer Name"
    for folder in (old, current, steam):
        client = folder / game_install.CLIENT
        client.parent.mkdir(parents=True)
        client.touch()
    registered.mkdir(parents=True)
    (registered / game_install.PATCHER).touch()
    for name in ("ProgramData", "ProgramFiles", "ProgramFiles(x86)"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(game_install, "local_drives", lambda: [other_drive, system_drive])
    monkeypatch.setattr(game_install, "registered_folders", lambda: [old / "Bin", registered, steam])
    assert game_install.detect_installs() == [registered, current, old]


@pytest.mark.skipif(
    os.name != "nt" or os.getenv("GITHUB_ACTIONS") != "true", reason="Uses a temporary A: drive on Windows CI"
)
def test_install_detection_finds_a_real_windows_drive_letter(tmp_path):
    if "A:\\" in (drive.upper() for drive in os.listdrives()):
        pytest.skip("A: is already assigned")
    folder = Path(r"A:\Spiele\Wizard101(DE)")
    client = folder / game_install.CLIENT
    subprocess.run(["subst", "A:", str(tmp_path)], check=True, capture_output=True)
    try:
        client.parent.mkdir(parents=True)
        client.touch()
        assert folder in game_install.detect_installs()
        assert game_install.install_folder(client) == folder
    finally:
        subprocess.run(["subst", "A:", "/d"], check=True, capture_output=True)


@pytest.fixture
def launch_environment(profile, monkeypatch, tmp_path):
    _, store, vault = profile
    install = tmp_path / "Wizard101 (DE)"
    (install / "Bin").mkdir(parents=True)
    (install / "Bin/WizardGraphicalClient.exe").write_bytes(b"synthetic-test-client")
    store.set("region_install_de", str(install))
    monkeypatch.setattr(backend.sys, "platform", "win32")
    monkeypatch.setattr(backend.psutil, "Process", lambda pid: SimpleNamespace(create_time=lambda: 10.0))
    monkeypatch.setattr(backend, "alive", lambda pid, created: (pid, created) == (42, 10.0))
    monkeypatch.setattr(backend, "window_handles", lambda: [(123, 42), (999, 88)])
    return store, vault, install


@pytest.mark.parametrize("native", [True, False])
@pytest.mark.parametrize("language", GAME_LANGUAGES)
def test_native_and_plain_quicklaunch_use_same_language(launch_environment, monkeypatch, native, language):
    store, vault, install = launch_environment
    stored = install / ("Bin" if native else game_install.CLIENT)
    store.set("region_install_de", f'"{stored}"')
    calls = []
    module = SimpleNamespace(launch=lambda *args: calls.append(args) or 42) if native else None
    monkeypatch.setattr(backend, "native_module", lambda: module)
    monkeypatch.setattr(
        backend.subprocess,
        "Popen",
        lambda args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(pid=42),
    )
    result = backend.launch(store, vault, "de", language=language)
    assert result["language"] == language
    assert result["region"] == "de" and result["hwnd"] == 123
    assert result["exe"] == str(install / game_install.CLIENT)
    if native:
        assert calls == [(str(install), "login-de.eu.wizard101.com:12000", language)]
    else:
        args, kwargs = calls[0]
        assert args == [
            str(install / "Bin/WizardGraphicalClient.exe"),
            *backend.launch_arguments("login-de.eu.wizard101.com", 12000, language),
        ]
        assert kwargs["cwd"] == install / "Bin"


def test_patcher_opens_from_the_configured_install_even_if_the_client_is_missing(
    launch_environment, monkeypatch
):
    store, vault, install = launch_environment
    (install / game_install.CLIENT).unlink()
    patcher = install / game_install.PATCHER
    patcher.touch()
    calls = []
    store.set("region_install_de", str(install / "Bin"))
    monkeypatch.setattr(backend.os, "startfile", lambda *args, **kwargs: calls.append((args, kwargs)), raising=False)
    monkeypatch.setattr(backend, "native_module", lambda: pytest.fail("Missing client must prevent launch"))
    with pytest.raises(ValueError, match="Spiel aktualisieren") as error:
        backend.launch(store, vault, "de")
    assert str(install / game_install.CLIENT) in str(error.value)
    assert backend.open_game_patcher(store, "de") == patcher
    assert calls == [((str(patcher),), {"cwd": str(install)})]


def test_early_client_exit_reports_the_executable_and_patch_action(launch_environment, monkeypatch):
    store, vault, install = launch_environment
    monkeypatch.setattr(backend, "native_module", lambda: SimpleNamespace(launch=lambda *_: 42))
    monkeypatch.setattr(backend, "alive", lambda *_: False)
    with pytest.raises(RuntimeError, match="vor dem Login beendet.*Spiel aktualisieren") as error:
        backend.launch(store, vault, "de")
    assert str(install / game_install.CLIENT) in str(error.value)


@pytest.mark.parametrize("native", [True, False])
def test_account_autologin_uses_profile_language_and_reports_sanitized_failure(
    launch_environment, monkeypatch, native
):
    store, vault, _ = launch_environment
    ident = store.save_account(vault, "Synthetic", "secret-user", "secret-password", "de")
    store.set("region_language_de", "us")
    launched, inputs = [], []
    module = SimpleNamespace(launch=lambda *args: launched.append(args) or 42) if native else None
    monkeypatch.setattr(backend, "native_module", lambda: module)
    monkeypatch.setattr(
        backend.subprocess, "Popen", lambda args, **kwargs: launched.append(args) or SimpleNamespace(pid=42)
    )
    def run(command, **kwargs):
        assert "secret-user" not in " ".join(command) and "secret-password" not in " ".join(command)
        inputs.append(json.loads(kwargs["input"]))
        assert kwargs["encoding"] == "utf-8" and kwargs["timeout"] == 35
        return SimpleNamespace(returncode=4, stdout='{"code":"input_failed","detail":"secret-password"}')

    monkeypatch.setattr(backend.subprocess, "run", run)
    monkeypatch.setattr(backend, "set_title", lambda *args: None)
    result = backend.launch(store, vault, "de", store.accounts()[0])
    assert (launched[0][2] == "us" if native else "-A" not in launched[0])
    assert inputs[0]["username"] == "secret-user"
    assert inputs[0]["hwnd"] == 123 and inputs[0]["ready_timeout"] == 15
    assert result["account_id"] == ident
    assert "[input_failed]" in result["warning"] and "secret-password" not in result["warning"]


@pytest.fixture
def worker(monkeypatch):
    clock, calls, owner = [0.0], [], [42]
    payload = {
        "pid": 42,
        "hwnd": 123,
        "created": 10.0,
        "username": "zauberä🧙",
        "password": "secret-password",
    }
    monkeypatch.setattr(
        backend.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))
    )
    monkeypatch.setattr(backend, "alive", lambda pid, created: (pid, created) == (42, 10.0))
    monkeypatch.setattr(backend, "window_handles", lambda: [(123, 42)])
    monkeypatch.setattr(backend.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))

    def send(hwnd, message, key, lparam, _flags, timeout, _result):
        assert hwnd == 123 and timeout == 1000
        calls.append((message, key, lparam, clock[0]))
        return 1

    def get_pid(hwnd, out):
        assert hwnd == 123
        ctypes.cast(out, ctypes.POINTER(ctypes.c_uint32))[0] = owner[0]
        return 1

    functions = {
        "SendMessageTimeoutW": send,
        "GetWindowThreadProcessId": get_pid,
        "IsWindowEnabled": lambda hwnd: hwnd == 123,
        "MapVirtualKeyW": lambda key, mode: {0x09: 0x0F, 0x0D: 0x1C}[key],
    }
    monkeypatch.setattr(backend, "user_function", lambda name, *args: functions[name])
    return calls, owner, functions


def test_worker_separates_credentials_when_the_client_only_handles_tab_as_a_key(worker, capsys):
    calls, _, _ = worker
    assert backend.login_worker() == 0
    fields = [bytearray(), bytearray()]
    active_field = 0
    submitted = []
    for message, key, details, at in calls:
        if message == 0x0102:
            assert at == (15 if active_field == 0 else 15.25)
            fields[active_field].extend(key.to_bytes(2, "little"))
        elif message == 0x0100 and key == 0x09:
            active_field = 1
        elif message == 0x0100 and key == 0x0D:
            submitted.append(tuple(field.decode("utf-16-le") for field in fields))
    assert submitted == [("zauberä🧙", "secret-password")]
    assert [event[:3] for event in calls if event[0] != 0x0102] == [
        (0x0100, 0x09, 0x000F0001),
        (0x0101, 0x09, 0xC00F0001),
        (0x0100, 0x0D, 0x001C0001),
        (0x0101, 0x0D, 0xC01C0001),
    ]
    assert not capsys.readouterr().out


def test_worker_stops_if_tab_delivery_fails_before_typing_password(worker, capsys):
    calls, _, functions = worker

    def fail_tab(_hwnd, message, key, *_):
        calls.append((message, key))
        return message == 0x0102

    functions["SendMessageTimeoutW"] = fail_tab
    assert backend.login_worker() == 4
    assert calls[-1] == (0x0100, 0x09)
    assert b"".join(key.to_bytes(2, "little") for message, key in calls[:-1]).decode("utf-16-le") == "zauberä🧙"
    assert json.loads(capsys.readouterr().out) == {"code": "input_failed"}


def test_worker_stops_if_window_changes_owner_during_input(worker, capsys):
    calls, owner, functions = worker

    def change_owner(_hwnd, _message, key, *_):
        calls.append(key)
        owner[0] = 999
        return 1

    functions["SendMessageTimeoutW"] = change_owner
    assert backend.login_worker() == 2
    assert calls == [ord("z")]
    assert json.loads(capsys.readouterr().out) == {"code": "identity"}


def test_worker_rejects_foreign_window_before_touching_client(worker, monkeypatch, capsys):
    calls, _, _ = worker
    monkeypatch.setattr(backend, "window_handles", lambda: [(123, 999)])
    assert backend.login_worker() == 2
    assert not calls
    assert json.loads(capsys.readouterr().out) == {"code": "identity"}
