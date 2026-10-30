# Native launcher adapter

Source: https://github.com/Deimos-Wizard101/Deimos-Wizard101/tree/99194d7d053b011f2db36bcc2d2bf6635acb7d7e/libs/wizlaunch

`src/launcher.rs`, `src/login.rs`, `src/errors.rs`: Deimos contributors, GPL-3.0-only.
Changes: own PyO3 interface and vault, explicit EU region argument, reject ambiguous login patterns, corrected description of the Python credential boundary.
No Deimos credential store or account metadata is used. Authentication does use a temporary game-memory hook. Windows client tests are required before a stable release; missing/ambiguous patterns fail closed.

The combined 6.0 distribution is provided under GPL-3.0-only. Original MIT portions retain their copyright and license in the repository root LICENSE. Full GPL text is in this directory and LICENSE-GPL-3.0. Build from the included source with maturin; Python/Rust are build-time tools only.
