"""Check helper dispatch inside the actual --windowed EXE, including its stdio."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import psutil

from wizq import __version__
from wizq.paths import Paths
from wizq.storage import Store
from wizq.updates import atomic_json, digest
from wizq.vault import Vault


def main():
    exe = Path("release") / f"WizQLauncher-v{__version__}.exe"
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        addon = root / "worker.py"
        addon.write_text(
            "import json,sys\nfor line in sys.stdin:\n p=json.loads(line)\n print(json.dumps({'type':'status','text':'pipes-ok'}),flush=True)\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(exe.resolve()), "--addon-worker", str(addon), "--addon-data", str(root)],
            input='{"type":"event","event":"host.ready","data":{}}\n',
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            creationflags=0x08000000,
        )
        assert result.returncode == 0, (result.returncode, result.stderr)
        assert json.loads(result.stdout.strip())["text"] == "pipes-ok"
        assert not (root / "data/launcher-v6.sqlite3").exists()
    print("Frozen worker pipes OK")
    with tempfile.TemporaryDirectory() as folder:
        # Exercise Unicode, spaces and an apostrophe without a command shell.
        root = Path(folder) / "Launcher's Test – Ordner"
        paths = Paths(root / "Profil")
        paths.prepare()
        store = Store(paths.database)
        vault = Vault(store)
        vault.initialize()
        for key in ("migration_checked",):
            store.set(key, True, meta=True)
        for key, value in (
            ("tutorial_seen", True),
            ("check_for_updates", False),
            ("discord_rich_presence", False),
            ("performance", "eco"),
        ):
            store.set(key, value)
        store.set("smoke_preserved", {"value": 42})
        account_id = store.save_account(vault, "Smoke", "synthetic-user", "synthetic-password", "de")
        snapshot = store.backup(paths.directory("updates") / "rollback")
        store.close()
        target = root / "Wiz Q Launcher.exe"
        source = paths.directory("updates") / "new.exe"
        helper = paths.directory("updates") / "relay.exe"
        for path in (target, source, helper):
            shutil.copy2(exe, path)
        old = subprocess.Popen([str(target), "--profile", str(paths.root), "--smoke-test"])
        created = psutil.Process(old.pid).create_time()
        job = paths.directory("updates") / "job-smoke.json"
        atomic_json(
            job,
            {
                "state": "ready",
                "target": str(target),
                "source": str(source),
                "sha256": digest(source),
                "pid": old.pid,
                "created": created,
                "profile": str(paths.root),
                "snapshot": str(snapshot),
                "smoke_test": True,
            },
        )
        relay = subprocess.run([str(helper), "--apply-update", str(job)], timeout=100, check=False)
        assert old.wait(timeout=30) == 0
        info = json.loads(job.read_text(encoding="utf-8"))
        if info.get("new_pid"):
            try:
                psutil.Process(info["new_pid"]).wait(timeout=30)
            except psutil.NoSuchProcess:
                pass
        assert relay.returncode == 0, info
        assert info["state"] == "healthy", info
        assert target.with_suffix(".previous.exe").exists()
        assert digest(target) == digest(source)
        store = Store(paths.database)
        try:
            vault = Vault(store)
            vault.unlock()
            assert store.get("last_successful_version", meta=True) == __version__
            assert store.get("smoke_preserved") == {"value": 42}
            assert store.credentials(vault, account_id)["password"] == "synthetic-password"
        finally:
            store.close()
    print("Frozen GUI, Unicode profile path, EXE exchange and data preservation OK")


if __name__ == "__main__":
    main()
