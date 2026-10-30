# 6.0.0-beta.1 implementation status
Updated 2026-10-30. This is the first executable code version of the rebuild, not a stable release declaration.

## Implemented
All six main pages, grouped drag/drop accounts, favorite/region filters, saved launch profiles, native backend interface, playtime heartbeat/recovery, local secure vault, legacy import, checked snapshots/recovery/export, update staging/relay, Discord integration, tutorial, contextual offline help, 20 themes, live Theme Creator, Stat Monitor, segmented FFmpeg replay/record, trusted addon worker protocol and example.
Old PySimpleGUI/source entrypoints have been removed. Legacy decoding is isolated and read-only.
The first transition may use a newly downloaded EXE, as accepted in the 6.0 planning.

## Verified locally
Core tests include a killed subprocess during an uncommitted write; exact/idempotent legacy statistics import; wrong password; complete import rollback; purpose-bound ciphertext; password rewrap; WAL-aware snapshots/rotation; profile lock; corrupt-file preservation; overlap/suspend/crash playtime; update asset selection, source validation and tampered-download rejection.
Qt tests instantiate all six pages, render all 20 themes and search Help. This is headless Qt rendering, not a Windows game session.

## Windows pipeline
The branch workflow installs the native Rust/PyO3 adapter, runs tests, packages the complete windowed EXE and tests its inherited stdin/stdout helper pipes.
Build artifacts are development downloads. Tag-based release workflow creates **draft** releases; it does not automatically publish a stable release.

## Required before stable
- Real US/DE and every advertised region/client version: install detection, spawn, login patterns, cleanup and multi-client matching.
- Actual Windows upgrade/rollback, paths containing non-ASCII/special characters, locks/antivirus, failure between exchange steps, and VM power-cut recovery.
- FFmpeg device/encoder checks, long recording/replay tests and supported audio-device behavior.
- Older PC/HiDPI/accessibility and global hotkey conflict tests.
- Full English UI, advanced third-party UI/settings API and explicit signing infrastructure are not complete in this first beta.
- Steam remains unvalidated; GPU sensor coverage currently includes optional NVIDIA CLI metrics, not all vendor sensors.
- Theme motion is intentionally bounded/simple; richer effects can be refined after performance measurement.

The initial plan remains the target specification, not a claim that every release-hardening item is already complete.
