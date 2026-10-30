# 6.0 profile and recovery
The profile root remains `%LOCALAPPDATA%/WizQLauncher`. The EXE can live elsewhere. Explicit exports may be written to another user-chosen directory.

## Authoritative storage
`data/launcher-v6.sqlite3`: settings, groups, account metadata, encrypted credential fields, sessions, activity intervals and migration markers.
Use Store methods/transactions. WAL + synchronous FULL + foreign keys are enabled. ProfileLock prevents two instances writing the same profile. The OS releases the lock after a killed process.
No GUI writes a complete cached config.json over later changes.

## Vault
Random 256-bit key; AES-GCM with per-write random 96-bit nonces and purpose/account-bound associated data.
Default Windows mode protects the key with per-user DPAPI, not machine-wide DPAPI.
Master-password mode uses scrypt (n=32768,r=8,p=1), random salt and AES-GCM key wrapping, without a persistent DPAPI bypass.
Wrong password, missing key or malformed ciphertext never creates an empty vault over the original.

DB snapshots preserve the key envelope. Normal Windows-protected snapshots therefore require the original Windows account/machine. Protected Export creates a snapshot with a new transport-password envelope; it does not change the live profile's protection.
No software can recover a lost true master password, protect against all same-user malware, guarantee Python RAM erasure or survive physical loss of all local copies.

## Legacy import
Reads config.json, data/accounts.enc.json and data/activity_24h.json without importing/executing the old GUI.
Supports the 5.5.1 PBKDF2/Fernet password mode, recognized placeholder mode, cached DPAPI and local-key mode; older plaintext account lists are decode-only input.
A vault-protected backup records the exact source bytes/hashes. The source files stay unchanged.
All accounts, their historical totals and import marker are written in one transaction. A failed account or wrong password does not mark migration complete. A committed marker makes retry idempotent.
Historical totals remain baseline fields. New sessions are summed separately, avoiding double import.
No data are invented when old totals contain no daily history. An abandoned active_since is not extended through downtime.

## Snapshots and restore
SQLite Backup API makes a consistent snapshot including committed WAL changes. Each candidate is fully checked before rename/rotation; the just-created valid copy is always retained.
Startup checks the DB. Corrupt DBs are not reset. If a usable snapshot exists, the dialog offers it.
Restore requires the profile lock and a closed connection. Original DB/WAL/SHM files are preserved together in a recovery directory before replacement.
External extension data, exported themes and large recordings are not part of DB-only snapshots; copy these directories separately if needed.

## Crash behavior
An interrupted transaction rolls back; committed settings survive ordinary process termination. Heartbeats persist playtime every ten seconds. A resumed launcher ends abandoned sessions at the last heartbeat. Long scheduling/suspend gaps are not credited.
Actual power-loss durability also depends on Windows/filesystem/storage honoring flushes. Process-kill tests are not a substitute for VM hard-reset and real hardware tests.

## EXE updates
Release assets must be complete `WizQLauncher-v<VERSION>.exe` files.
Download checks the repository URL, maximum size, exact byte count and SHA256 against HTTPS GitHub release metadata. A digest mismatch leaves the old EXE unchanged.
A detached helper waits for the exact old process (PID and creation time), stages in the target directory, retains a previous EXE, and starts the replacement.
Before apply, a DB snapshot is saved. If the new process exits before reporting readiness, the helper restores the snapshot and old EXE under the profile lock.
A still-running process is not killed or rolled back just because the user is taking time to unlock it. Separate publisher-signature infrastructure and interrupted-helper recovery beyond this journaled beta flow remain release-hardening work.
