# Local API integration

Base URL: `http://127.0.0.1:8765`. Run the service in the logged-in Windows desktop session that runs EZCAD2. This is not a remote printer protocol and is not a Windows service running in Session 0.

## Session and origin

`GET /api/status` returns:

```json
{
  "available": {"red": true, "stop": false, "mark": true},
  "title": "EzCad-Lite - example.ezd",
  "pending": false,
  "message": "...",
  "selected": "...",
  "token": "session-token"
}
```

`available` means that a matching enabled UI control was found, not that hardware readiness was verified. `selected` is the requested filename, not proof of the loaded document. Reading status sends no hardware command.

Mutations use `POST /api/action` with:

```text
Host: 127.0.0.1:8765
Origin: http://127.0.0.1:8765
Content-Type: application/json
X-Panel-Token: <token from status>
```

The token changes when the service restarts. It is not a user identity or a production authorization system. Other website origins and cross-site browser requests are rejected; CORS is not enabled. Do not solve remote integration by opening the listening address or allowing all origins. A future hosted-site integration needs explicit pairing, narrow allowed origins, command authorization, and a production workflow.

## Request IDs

Each action contains an `id` string of 8–100 characters; UUIDs are recommended. Repeating the same ID and identical payload returns the cached result without another UI action. Reusing an ID with different content is rejected. IDs and results are kept in memory for this service lifetime, with a 10,000-request limit. They are not durable across a restart.

If the response is lost, do not issue the same intended operation under a new ID. Inspect EZCAD2 and reconcile the operation; an uncertain outcome must not be interpreted as failure or permission to print again.

## Actions

### Red / Stop

```json
{"id":"<uuid>","action":"red"}
```

Use `"action":"stop"` for Stop. No automatic retry is performed. Stop remains a software request and cannot replace a hardware emergency stop.

### Load an original local file

```json
{"id":"<uuid>","action":"load","path":"C:\\Jobs\\panel.ezd"}
```

The path is on the **laser computer**. This is the preferred option for files with local dependencies.

### Upload a design

```json
{"id":"<uuid>","action":"load","name":"panel.ezd","content":"<base64 bytes>"}
```

Maximum decoded size: 20 MiB. Files are stored under `runtime/web_uploads/` with generated names. The original name is display metadata only. Referenced assets are not included automatically. File content validity is decided by EZCAD2.

Loading is asynchronous. `pending` stays true while the service waits up to 120 seconds for the Open dialog. Save/Discard/Cancel prompts must be handled manually in EZCAD2. Other commands except Stop are rejected during this wait. `pending:false` alone is not proof of successful loading; check `message` and inspect the actual design.

### Mark: explicit two-step confirmation

First request:

```json
{"id":"<uuid-1>","action":"prepare_mark"}
```

Response includes `ticket` and the current `title`. **This does not mark.** Show the title to the operator and ask for explicit confirmation. Then, only after confirmation:

```json
{"id":"<uuid-2>","action":"mark","ticket":"<ticket>"}
```

Tickets expire after 30 seconds, are consumed once, and are tied to the observed process/window/button/title. A changed target causes rejection. A new preparation invalidates the previous ticket; Red, Stop, and Load also invalidate tickets. Editing a document without changing its title may not be detected, so prevent competing operator edits during confirmation.

## Responses and completion

Action responses contain `ok` and usually `message`. Successful preparation also returns `ticket` and `title`. Domain-level command failures may have HTTP 200 with `ok:false`; inspect both the HTTP status and JSON body. Invalid HTTP requests return 400, origin/token violations 403, and unknown paths 404.

`ok:true` means the application accepted the request / posted the UI message. It does **not** mean physical marking completed. There is no job-complete callback in this version. Production integration must add an independent completion/inspection signal and durable board/serial state rather than consuming a serial when this API responds.

## Embedding in your own software

- For a local UI, reuse the same-origin frontend or host your operator page through this local service.
- For another trusted local process, implement this contract, keep the session token in memory, and preserve the human Mark-confirmation flow.
- For your hosted web application, first add a separately reviewed pairing/authentication design. The current server intentionally refuses direct cross-origin control.
- Keep offline tests using `FakeUI` in `test_web_panel.py`; never use live hardware for automated CI.
