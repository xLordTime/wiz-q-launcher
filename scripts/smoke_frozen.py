"""Check helper dispatch inside the actual --windowed EXE, including its stdio."""

import json
import subprocess
import tempfile
from pathlib import Path

from wizq import __version__


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


if __name__ == "__main__":
    main()
