import ctypes
import io
import json
from types import SimpleNamespace

import pytest

from wizq import backend
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
    if native:
        assert calls == [(str(install), "login-de.eu.wizard101.com:12000", language)]
    else:
        args, kwargs = calls[0]
        assert args == [
            str(install / "Bin/WizardGraphicalClient.exe"),
            *backend.launch_arguments("login-de.eu.wizard101.com", 12000, language),
        ]
        assert kwargs["cwd"] == install / "Bin"


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
