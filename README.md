# Wiz Q Launcher 6
**Complete PySide6 rebuild — development beta on `Version-6.0`.**

A local Windows launcher for Wizard101: multi-account launch, groups and drag & drop, playtime, 20 themes, optional addons, Discord and a crash-resistant profile. This branch is not a stable replacement until real Windows/US/DE client tests have been completed.

## Start
Windows users use the complete EXE from a successful **Version 6 Windows Build** artifact. Python and Rust are not required to run the EXE. No 6.0 stable release is published automatically.

The first 5.x → 6.0 transition may download a new EXE and require starting it once. Subsequent 6.x updates use the new verified-download/relay flow. The profile remains in **%LOCALAPPDATA%/WizQLauncher**.

First start:
1. Choose Windows account protection or a real master password.
2. If found, unlock and import your old profile. Source files are not modified.
3. Choose game folders per region under Settings → Launcher & Regionen.
4. Add/select accounts and launch. F1 opens offline help.

## What is implemented
- Launch, Account Management, Playtime, Addons, Settings, Help.
- Nickname/username/password, groups, drag & drop, favorites, saved launch selections.
- SQLite WAL/FULL, serialized transactions, checked rotating snapshots, original-preserving restore.
- AES-GCM vault, per-user DPAPI or scrypt-wrapped master key; no fixed password fallback.
- Read-only import of the 5.5.1 encrypted formats and historical playtime totals.
- PID + creation time session identity, heartbeat checkpoints and no offline credit after crashes.
- Deimos-derived native start/login adapter, without a required wizwalker installation.
- Discord RPC/yield-to-game and optional encrypted webhook.
- Stat Monitor, Clips and Record (external FFmpeg), Theme Creator and 20 vector themes.
- Trusted custom addon workers and example SDK.
- Explicit GitHub asset selection, size/SHA256 verification, restart helper and rollback snapshots.

**Limits:** Native login, recording, global hotkeys and real EXE replacement need Windows validation. Imported region entries are not proof of current region/client compatibility. Steam is not yet a validated flow. The first beta UI is German; an imported English preference is retained for later translation. Updates currently rely on the HTTPS GitHub API asset digest; no separate publisher signature is configured. Custom code workers are not a security sandbox.

## Development on Windows
Use Python 3.12 x64 and Rust stable (MSVC build tools).
```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip install ./native
.venv\Scripts\python -m pytest -q
.venv\Scripts\python main.py
.venv\Scripts\python build.py
```
Or run `make_exe.bat`. It stops on dependency/test/build errors.

Qt/core development on other systems can run with an explicit disposable profile:
```sh
python main.py --profile /path/to/development-profile
QT_QPA_PLATFORM=offscreen python -m pytest -q
```
A non-Windows run requires master-password protection and cannot launch Wizard101.

`--safe-mode` disables addons/custom themes without resetting data.
Ctrl+1…6 changes page, Ctrl+L locks the vault, F1 opens Help, Ctrl+Q exits.
Windows global hotkeys: Ctrl+Alt+L starts the selected accounts, Ctrl+Alt+C saves a replay clip. Occupied combinations are not taken from another app.

## Documentation
- [Beta status, tests and limits](documentation/V6_BETA.md)
- [Full rebuild specification](documentation/VERSION_6_PLAN.md)
- [Create addons](documentation/ADDON_SDK.md)
- [Storage, migration and recovery](documentation/V6_STORAGE.md)
- [Native source provenance](native/PROVENANCE.md)

Other older documents describe the 5.x interface; they are historical reference only. The obsolete PySimpleGUI modules were removed; the importer does not execute their code.

## Licensing
The combined 6.0 application and new core are GPL-3.0-only because the native adapter derives from Deimos GPL code. See [LICENSE](LICENSE), [original MIT notices](LICENSE-MIT), and [third-party inventory](THIRD_PARTY.md).
The original MIT copyright notice is retained. Complete native adapter source and its pinned upstream origin are included under `native/`.





