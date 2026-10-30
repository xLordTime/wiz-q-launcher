import hashlib

import pytest

from wizq import updates


class Response:
    status_code = 200

    def __init__(self, content=b"", data=None):
        self.content, self.data = content, data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def json(self):
        return self.data

    def iter_content(self, *args):
        yield self.content


def asset(content):
    return {
        "url": "https://github.com/xLordTime/wiz-q-launcher/releases/download/v6.0.1/WizQLauncher-v6.0.1.exe",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "version": "6.0.1",
    }


def test_asset_selection_skips_helper_exe(monkeypatch):
    content = b"MZ-test"
    info = asset(content)
    release = {
        "tag_name": "v6.0.1",
        "assets": [
            {"name": "helper.exe"},
            {
                "name": "WizQLauncher-v6.0.1.exe",
                "browser_download_url": info["url"],
                "size": len(content),
                "digest": "sha256:" + info["sha256"],
            },
        ],
    }
    monkeypatch.setattr(updates.requests, "get", lambda *a, **k: Response(data=release))
    assert updates.check()["sha256"] == info["sha256"]


def test_hash_mismatch_leaves_no_executable(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.requests, "get", lambda *a, **k: Response(b"tampered"))
    with pytest.raises(ValueError):
        updates.download(asset(b"original"), tmp_path)
    assert not list(tmp_path.iterdir())


def test_complete_download_validated(tmp_path, monkeypatch):
    content = b"MZ-test-content"
    monkeypatch.setattr(updates.requests, "get", lambda *a, **k: Response(content))
    path = updates.download(asset(content), tmp_path)
    assert path.read_bytes() == content
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize(
    "change",
    [
        {"url": "http://github.com/xLordTime/wiz-q-launcher/releases/download/v6.0.1/a.exe"},
        {"url": "https://github.com/other/repo/releases/download/v6.0.1/a.exe"},
        {"sha256": ""},
    ],
)
def test_untrusted_metadata_rejected(change):
    info = asset(b"MZ")
    info.update(change)
    with pytest.raises(ValueError):
        updates.validate_asset(info)


def test_executable_start_failure_restores_program_and_database(tmp_path, monkeypatch):
    import os

    from wizq.paths import Paths
    from wizq.storage import Store

    paths = Paths(tmp_path / "profile")
    paths.prepare()
    store = Store(paths.database)
    store.set("preserved", "old-compatible")
    snapshot = store.backup(paths.directory("updates") / "rollback")
    store.set("preserved", "pre-update-changed")
    store.close()
    target = tmp_path / "Launcher.exe"
    target.write_bytes(b"MZ-old")
    source = paths.directory("updates") / "download.exe"
    source.write_bytes(b"MZ-new")
    job = paths.directory("updates") / "job-test.json"
    updates.atomic_json(
        job,
        {
            "state": "ready",
            "target": str(target),
            "source": str(source),
            "sha256": updates.digest(source),
            "pid": os.getpid(),
            "created": 0,
            "profile": str(paths.root),
            "snapshot": str(snapshot),
        },
    )
    calls = []

    def spawn(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise OSError("simulated invalid executable")
        return object()

    monkeypatch.setattr(updates.subprocess, "Popen", spawn)
    updates.apply_worker(job)
    assert target.read_bytes() == b"MZ-old"
    assert __import__("json").loads(job.read_text())["state"] == "rolled-back"
    store = Store(paths.database)
    try:
        assert store.get("preserved") == "old-compatible"
    finally:
        store.close()
