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


def test_account_autologin_uses_profile_language_and_reports_sanitized_failure(
    launch_environment, monkeypatch
):
    store, vault, _ = launch_environment
    ident = store.save_account(vault, "Synthetic", "secret-user", "secret-password", "de")
    store.set("region_language_de", "us")
    launched, inputs, enabled = [], [], []
    monkeypatch.setattr(
        backend, "native_module", lambda: SimpleNamespace(launch=lambda *args: launched.append(args) or 42)
    )
    monkeypatch.setattr(
        backend, "user_function", lambda *args: lambda hwnd, flag: enabled.append((hwnd, flag))
    )

    def run(command, **kwargs):
        assert "secret-user" not in " ".join(command) and "secret-password" not in " ".join(command)
        inputs.append(json.loads(kwargs["input"]))
        assert kwargs["encoding"] == "utf-8" and kwargs["timeout"] == 35
        return SimpleNamespace(returncode=4, stdout='{"code":"login_missing","detail":"secret-password"}')

    monkeypatch.setattr(backend.subprocess, "run", run)
    monkeypatch.setattr(backend, "set_title", lambda *args: None)
    result = backend.launch(store, vault, "de", store.accounts()[0])
    assert launched[0][2] == "us" and inputs[0]["username"] == "secret-user"
    assert inputs[0]["hwnd"] == 123 and inputs[0]["ready_timeout"] == 15
    assert result["account_id"] == ident
    assert "[login_missing]" in result["warning"] and "secret-password" not in result["warning"]
    assert enabled == [(123, 1)]


@pytest.fixture
def worker(monkeypatch):
    clock, enabled, calls = [0.0], [], []
    payload = {
        "pid": 42,
        "hwnd": 123,
        "created": 10.0,
        "username": "secret-user",
        "password": "secret-password",
    }
    monkeypatch.setattr(
        backend.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))
    )
    monkeypatch.setattr(backend, "alive", lambda pid, created: (pid, created) == (42, 10.0))
    monkeypatch.setattr(backend, "window_handles", lambda: [(123, 42)])
    monkeypatch.setattr(backend.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(backend.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    monkeypatch.setattr(
        backend, "user_function", lambda *args: lambda hwnd, flag: enabled.append((hwnd, flag))
    )
    return clock, enabled, calls


def test_worker_retries_only_pre_dispatch_initialization_and_reenables_input(worker, monkeypatch, capsys):
    clock, enabled, calls = worker

    def login(*args):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("Login failed: CLIENT_NOT_READY")

    monkeypatch.setattr(backend, "native_module", lambda: SimpleNamespace(login=login))
    assert backend.login_worker() == 0
    assert len(calls) == 2 and clock[0] == 2.5
    assert enabled == [(123, 0), (123, 1)]
    assert not capsys.readouterr().out


@pytest.mark.parametrize(
    "message,code",
    [
        ("LOGIN_PATTERN ambiguous", "login_ambiguous"),
        ("HOOK_PATTERN ambiguous", "hook_ambiguous"),
        ("OpenProcess: Access denied", "permission"),
        ("Timed out waiting for login bytecode to execute", "hook_timeout"),
        ("secret-user secret-password", "unsupported"),
    ],
)
def test_worker_does_not_repeat_dispatch_or_leak_exceptions(worker, monkeypatch, capsys, message, code):
    _, enabled, calls = worker

    def login(*args):
        calls.append(args)
        raise RuntimeError(message)

    monkeypatch.setattr(backend, "native_module", lambda: SimpleNamespace(login=login))
    assert backend.login_worker() == 4
    assert len(calls) == 1
    assert enabled == [(123, 0), (123, 1)]
    output = capsys.readouterr()
    assert json.loads(output.out) == {"code": code}
    assert "secret-" not in output.out + output.err


def test_worker_stops_waiting_for_missing_pattern(worker, monkeypatch, capsys):
    clock, enabled, calls = worker

    def login(*args):
        calls.append(args)
        raise RuntimeError("LOGIN_PATTERN not found")

    monkeypatch.setattr(backend, "native_module", lambda: SimpleNamespace(login=login))
    assert backend.login_worker() == 4
    assert clock[0] == 15 and len(calls) > 1
    assert json.loads(capsys.readouterr().out) == {"code": "login_missing"}
    assert enabled[-1] == (123, 1)


def test_worker_rejects_foreign_window_before_touching_client(worker, monkeypatch, capsys):
    _, enabled, _ = worker
    monkeypatch.setattr(backend, "window_handles", lambda: [(123, 999)])
    assert backend.login_worker() == 2
    assert not enabled
    assert json.loads(capsys.readouterr().out) == {"code": "identity"}
