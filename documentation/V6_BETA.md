# 6.0.0-beta.3 implementation status
Updated 2026-10-30. The native desktop beta replaces the first web-like layout; it is not a stable release declaration.

## Selection fix beta.3
High-contrast active/inactive row selection across all themes; explicitly painted checkmarks; a Startauswahl text column, checked-row emphasis, detail confirmation and account count on the start button. Render tests inspect real checkbox pixels and unfocused row backgrounds in all 23 presets, plus contrast checks for custom themes.

## Desktop beta.2
Native menu/toolbar, Explorer tree, interactive breadcrumb segment/dropdown navigation, shared back/forward/up history, compact account/instance tables, property dialogs, resizable/saved splitters and three additional desktop themes. Filtered-out checked accounts are remembered but never launched silently. Quicklaunch chooses a region independently of the account filter.

See [the German testing guide](V6_TESTING.md).

## Implemented
All six main pages, grouped drag/drop accounts, favorite/region filters, saved launch profiles, native backend interface, playtime heartbeat/recovery, local secure vault, legacy import, checked snapshots/recovery/export, update staging/relay, Discord integration, tutorial, contextual offline help, 20 themes, live Theme Creator, Stat Monitor, segmented FFmpeg replay/record, trusted addon worker protocol and example.
Old PySimpleGUI/source entrypoints have been removed. Legacy decoding is isolated and read-only.
The first transition may use a newly downloaded EXE, as accepted in the 6.0 planning.

## Verified locally
Core tests include a killed subprocess during an uncommitted write; exact/idempotent legacy statistics import; wrong password; complete import rollback; purpose-bound ciphertext; password rewrap; WAL-aware snapshots/rotation; profile lock; corrupt-file preservation; overlap/suspend/crash playtime; update asset selection, source validation and tampered-download rejection.
Qt tests instantiate all six pages, render all 20 previous themes and the three desktop presets, search Help, exercise path/tree/history synchronization, group deletion, filtered launch selection and Quicklaunch region/count. Desktop screenshots use synthetic accounts. The layout is checked at 1000×700. This is headless Qt rendering, not a Windows game session.

## Windows pipeline
The native Rust/PyO3 adapter has compiled successfully on Windows; the first full Windows run passed 22 core/Qt/DPAPI/native tests and produced an EXE with working inherited stdin/stdout helper pipes.
The branch workflow also exercises the packaged GUI and a real same-version EXE exchange/healthy restart against a disposable DPAPI profile, preserving synthetic credentials and settings, including Unicode/spaces/apostrophes in paths. This does not replace real game-client tests.
Build artifacts are development downloads. Explicit `release: ` commits on Version-6.0 and v6 tags run the release pipeline. Beta/alpha/RC releases publish after validation with the EXE, checksums and test guide. Stable versions remain drafts.

## Required before stable
- Real US/DE and every advertised region/client version: install detection, spawn, login patterns, cleanup and multi-client matching.
- Actual Windows upgrade/rollback, paths containing non-ASCII/special characters, locks/antivirus, failure between exchange steps, and VM power-cut recovery.
- FFmpeg device/encoder checks, long recording/replay tests and supported audio-device behavior.
- Older PC/HiDPI/accessibility and global hotkey conflict tests.
- Full English UI, advanced third-party UI/settings API and explicit signing infrastructure are not complete in this first beta.
- Steam remains unvalidated; GPU sensor coverage currently includes optional NVIDIA CLI metrics, not all vendor sensors.
- Theme motion is intentionally bounded/simple; richer effects can be refined after performance measurement.

The initial plan remains the target specification, not a claim that every release-hardening item is already complete.
