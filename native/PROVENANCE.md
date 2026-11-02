# Native launcher adapter

Source: https://github.com/Deimos-Wizard101/Deimos-Wizard101/tree/99194d7d053b011f2db36bcc2d2bf6635acb7d7e/libs/wizlaunch

`src/launcher.rs`, `src/login.rs`, `src/errors.rs`: Deimos contributors, GPL-3.0-only.
Changes: own PyO3 interface and vault; game-language argument independent of the login server (US English omits -A); validated dispatcher instructions/RIP targets with variable stack-local displacement; validated RootWindowHook instruction boundary; separate missing/ambiguous failures and a pre-dispatch client-pointer readiness check. Ambiguous patterns still fail closed. Python credentials remain isolated in a worker and never enter process arguments.

RootWindowHook instruction reference: https://github.com/StarrFox/wizwalker/blob/12e64737c5a1a6bc83daf17cbde3f649ce716ff5/wizwalker/memory/hooks.py (`RootWindowHook.bytecode_generator`, mov rcx,[r15+D8]). The existing Deimos code already cites this hook; the validator now checks its register-based instruction instead of treating all seven bytes as wildcards. No wizwalker dependency or credential store is added.
No Deimos credential store or account metadata is used. Authentication does use a temporary game-memory hook. Windows client tests are required before a stable release; missing/ambiguous patterns fail closed.

The combined 6.0 distribution is provided under GPL-3.0-only. Original MIT portions retain their copyright and license in the repository root LICENSE. Full GPL text is in this directory and LICENSE-GPL-3.0. Build from the included source with maturin; Python/Rust are build-time tools only.
