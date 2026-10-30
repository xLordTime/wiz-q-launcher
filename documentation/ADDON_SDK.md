# Addon SDK v1 — implemented worker protocol
Status: development beta. Only the protocol described here is implemented; no unrestricted Host API or automatic addon marketplace exists.

## Minimal addon
Copy `examples/addons/session-counter` to `%LOCALAPPDATA%/WizQLauncher/addons/session-counter`.
Restart the launcher. Open Addons → Verwalten and deliberately enable the extension.

`addon.json`:
```json
{"id":"session-counter","name":"Session Counter","version":"1.0.0","api_version":1,"entrypoint":"worker.py","capabilities":["sessions.read","ui.cards","storage"]}
```
The directory name must equal id. The entrypoint is a Python file directly in that directory. Manifest ≤64 KiB; entrypoint ≤1 MiB. Only capability names listed above are accepted.

## Runtime
The host starts a separate process using its bundled Python and `--addon-worker`; end users do not need a separate Python installation for stdlib-only extensions.
The normal profile GUI/vault is never initialized in this mode.
Use stdlib or modules already shipped in the launcher; there is no implicit pip installation.
The absolute writable addon data directory is in `WIZQ_ADDON_DATA`.
No password, webhook URL, or vault key is provided through the host protocol.

Worker process **does not mean sandbox**. Code runs with the user's Windows permissions and can import Python/file/network APIs. Capabilities filter host messages, not Windows permissions. Install only reviewed/trusted source. Extensions require activation each launcher session; Safe Mode skips discovery.

## JSON Lines
stdin and stdout use UTF-8 JSON objects, one per line. Flush stdout after each packet. Do not print debugging output to stdout; stderr is drained without displaying secret-bearing tracebacks. Messages are limited to 64 KiB; malformed/oversized output stops the worker.

Host → addon:
```json
{"type":"event","event":"host.ready","data":{}}
{"type":"event","event":"session.started","data":{"region":"de","pid":1234}}
{"type":"event","event":"session.ended","data":{"region":"de","seconds":120.0}}
{"type":"event","event":"host.stop","data":{}}
```
Session events are sent only to `sessions.read` addons. A started event means a client start completed; it is not a server-authentication success assertion. Recovered historical sessions do not re-emit start notifications.

Addon → host:
```json
{"type":"status","text":"2 sessions started this run"}
```
Status text is plain text, bounded to 2000 characters and shown in the addon management status area. Arbitrary HTML, native Qt widget injection, arbitrary host SQL and secrets APIs are not exposed.
The current API does not yet provide interactive third-party tabs or host-persisted custom settings. Built-in addons have their own reviewed Qt pages.

## Lifecycle and failures
Parse input in a loop; exit on host.stop or EOF. Do not block indefinitely while handling an event. On Disable, the host requests stop, then terminates/kills a worker that does not finish promptly. Addon startup/protocol errors are shown without crashing the launcher.
Custom addon metadata or content changes require another explicit activation. Child code and imported modules are trusted code, regardless of the entrypoint fingerprint.

For durable addon files, write a temporary file, flush/fsync, then os.replace it. Keep a last good copy for recovery. Own extension data are separate from the core database and are not included in the current core-only DB backup.
