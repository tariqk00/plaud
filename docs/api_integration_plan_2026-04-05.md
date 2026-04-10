# Plaud Direct API Integration Plan — 2026-04-05

## Goal

Replace the current Gmail email polling pipeline with a direct pull from Plaud's API. The Gmail pipeline is fragile (depends on email delivery timing, email format changes, PLAUD-AutoFlow label behavior) and produces malformed filenames. A direct API pull gives structured data with real recording metadata.

---

## 1. Authentication

### How It Works

Plaud's API (`api.plaud.ai`) uses a long-lived JWT bearer token. There is no official public auth endpoint — the token is obtained by logging in at `web.plaud.ai` and extracting it from browser network traffic.

**The token does not expire on a fixed schedule.** Based on reverse-engineering by multiple projects (arbuzmell/plaud-api, giovi321/plaud-unofficial-api), the token is a long-lived session token that persists until the user logs out or invalidates the session. In practice, users report tokens lasting weeks to months.

**No programmatic refresh mechanism exists.** There is no `/auth/refresh` endpoint. When the token expires, the only option is to log back in to `web.plaud.ai` and extract a new one.

### How to Extract the Token

1. Open `web.plaud.ai` and sign in
2. Open DevTools (F12) → Network tab
3. Filter by XHR/Fetch requests to `api.plaud.ai`
4. Click any request → Headers → find `Authorization: bearer <token>`
5. Copy the token value (without the "bearer " prefix)

Alternatively:
1. Open DevTools → Application → Local Storage → `https://web.plaud.ai`
2. Look for the token key (varies by Plaud's auth implementation)

### Token Storage on the NUC

Store in `/home/tariqk/github/tariqk00/plaud/config/plaud_token` (plain text, gitignored — add to `.gitignore`).

Also supported via environment variable `PLAUD_TOKEN` for systemd service injection via a secrets env file (e.g. `~/.config/plaud-secrets.env`).

### Token Rotation Strategy

Since there's no auto-refresh, implement a monitoring check:
- On each run, catch `401 AuthenticationError` and send a Telegram alert via `send_message(..., service="plaud-automation")` asking the user to refresh the token
- Keep a `last_successful_run` timestamp; if > 14 days without success, send a proactive "token may be expiring soon" alert
- Document the manual refresh procedure in `plaud/docs/token_refresh.md`

---

## 2. Available API Endpoints

Base URL: `https://api.plaud.ai`

All requests require:
- `Authorization: bearer <token>`
- `Content-Type: application/json`
- `Origin: https://web.plaud.ai`
- `Referer: https://web.plaud.ai/`
- `app-platform: web`
- `edit-from: web`

A random `r` parameter is added to each request body/params (anti-caching artifact from Plaud's web client).

### Core Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /file/simple/web` | GET | List recordings (paginated). Params: `skip`, `limit`, `is_trash=0`, `sort_by=start_time`, `is_desc=true` |
| `POST /file/list` | POST | Get full details for batch of recording IDs. Body: `[file_id, ...]`. Returns `trans_result`, `ai_content`, etc. |
| `GET /file/temp-url/{file_id}` | GET | Get temporary S3 presigned URL for audio download |
| `PATCH /file/{file_id}` | PATCH | Update recording (start transcription, save results) |
| `POST /ai/transsumm/{file_id}` | POST | Get/trigger AI transcription+summary status |
| `GET /speaker/list` | GET | List all known speakers |
| `POST /speaker/sync` | POST | Sync speaker data |
| `GET /filetag/` | GET | List all tags (folders in Plaud) |

### Key Data Fields Returned by `/file/list`

Each recording object contains:
- `id` — unique file ID (used as primary key for dedup)
- `filename` — display name set in Plaud app
- `start_time` — Unix timestamp (ms) of recording start — **use this for date**
- `duration_ms` — recording duration
- `filesize` — bytes
- `has_transcription` — boolean
- `has_summary` — boolean
- `trans_result` — array of transcript segments with `speaker`, `text`, `start_time_ms`, `end_time_ms`
- `ai_content` — markdown string of AI summary
- `tag_ids` — array of tag IDs (Plaud folder/category)

---

## 3. New Pipeline Design

### Current Pipeline (Gmail)

```
Gmail: poll for unread from no-reply@plaud.ai
  → extract subject, date, body, attachments
  → parse date from subject (fragile)
  → upload .md to Filing Cabinet/Plaud
  → upload Recording.txt attachment to same folder
  → archive email thread
```

**Problems:**
- Date parsing from email subject is fragile (produces "Monday at  AM" malformed names)
- Dependent on PLAUD-AutoFlow email delivery (can be delayed or filtered)
- No dedup — same recording uploaded multiple times if email re-sent
- Targets wrong Drive folder (Filing Cabinet instead of Second Brain)

### New Pipeline (Direct API)

```
Plaud API: GET /file/simple/web (list since last_seen_id or since last_run timestamp)
  → for each new recording:
      → GET /file/list [id] to get full details (transcript + summary inline)
      → derive filename from start_time + filename field
      → upload .md (summary) to 01 - Second Brain/Plaud
      → upload .txt (transcript) to 01 - Second Brain/Plaud
      → optionally: GET /file/temp-url/{id} and download audio
  → save last_seen_id or last_run timestamp to state file
```

### Dedup Strategy

Use `recording.id` (Plaud's internal file ID) as the dedup key:
- Maintain a state file at `plaud/data/processed_ids.json` — a JSON set of processed Plaud file IDs
- On each run, skip any recording whose ID is already in the set
- This is more reliable than filename comparison (same recording could be processed with different names)

### Filename Generation

Use `start_time` (Unix ms) from the API response for the date — this is the actual recording date, not the email delivery date:

```python
from datetime import datetime, timezone
dt = datetime.fromtimestamp(recording.start_time / 1000, tz=timezone.utc).astimezone()
date_str = dt.strftime("%Y-%m-%d")
topic = recording.filename or "Recording"
# Sanitize topic: remove illegal Drive chars
topic = re.sub(r'[\\/:*?"<>|]', '-', topic).strip()
md_filename = f"{date_str} - {topic}.md"
txt_filename = f"{date_str} - {topic} - Transcript.txt"
```

### Markdown Output Format

Mirror the existing format from `automation.py` for consistency:

```markdown
# {topic}

**Date:** {date_str}
**Duration:** {duration_display}
**Source:** Plaud Direct API

---

## Summary

{ai_content}

## Transcript

{formatted transcript segments with speaker labels}
```

---

## 4. Changes to Existing Files

### New File: `plaud/src/plaud_client.py`

A lightweight wrapper around the Plaud API — no external dependency on `arbuzmell/plaud-api` (keeps the plaud repo self-contained). Implement only what's needed:
- `PlaudClient(token)` — constructor
- `list_recordings(since_timestamp=None, limit=50)` — calls `GET /file/simple/web`
- `get_recording_details(file_ids)` — calls `POST /file/list`
- `get_audio_url(file_id)` — calls `GET /file/temp-url/{file_id}`

Session setup: use `requests.Session` with the browser headers from the reverse-engineering analysis (see `session.py` in arbuzmell/plaud-api for the exact header set needed).

### Modified File: `plaud/src/automation.py`

Add a new `main_direct()` function that uses `PlaudClient` instead of `gmail_mcp`. Keep `main()` (Gmail) intact until the direct pipeline is validated. Switch the default entry point by adding a `--mode direct|gmail` flag or environment variable `PLAUD_MODE`.

Key changes:
- Import `PlaudClient` from `src.plaud_client`
- Load `processed_ids.json` state
- Call `list_recordings(since_timestamp=last_run)` 
- For each new recording: build content, upload via existing `drive_mcp` helpers
- Save updated state

Target Drive folder: change from `"Filing Cabinet/Plaud"` to `"01 - Second Brain/Plaud"`.

### Modified File: `plaud/bin/run_automation.sh`

Add `PLAUD_TOKEN` export from the secrets file before invoking the Python script:

```bash
if [ -f "$HOME/.config/plaud-secrets.env" ]; then
    export $(grep -v '^#' "$HOME/.config/plaud-secrets.env" | xargs)
fi
```

### New File: `plaud/data/processed_ids.json`

State file, gitignored. Format: `{"processed_ids": ["id1", "id2", ...], "last_run": "2026-04-05T07:00:00"}`.

### No Changes Needed

- `plaud/src/mcp_server/drive.py` — keep as-is; `upload_file` and `upload_binary_file` work fine
- `plaud/src/mcp_server/gmail.py` — keep for now; deprecate after direct pipeline is validated
- systemd service/timer files — no changes needed; `run_automation.sh` is the entry point

---

## 5. OpenClaw Skill vs. Lightweight Client

### Option A: Install the OpenClaw Skill (`leonardsellem/plaud-unofficial`)

The OpenClaw skill (also available as `arbuzmell/plaud-api` on PyPI) is a full-featured MCP server that exposes Plaud API operations. The hanzoskill package (`hanzoskill/plaud-unofficial`) appears to be the OpenClaw wrapper around the same API.

**Pros:** Full-featured, tested, handles speakers/tags/pagination  
**Cons:** Adds an MCP dependency, introduces external package to manage, overkill for a cron job, OpenClaw skill activation requires network connectivity to `openclawskills.best`

### Option B: Build `plaud_client.py` Directly (Recommended)

**Pros:**
- Self-contained in the plaud repo
- No new pip dependencies beyond `requests` (already available in the venv)
- Only implements the 3 methods actually needed
- Full control over error handling and token management
- No MCP server overhead for a scheduled cron task

**Recommendation: Option B.** The API surface needed is small (list + details + optional audio URL). The session.py and recordings.py from arbuzmell/plaud-api provide the exact implementation pattern. Building a 150-line `plaud_client.py` is the right call for a scheduled automation script.

If interactive/ad-hoc access from Claude Code is desired later, the OpenClaw skill or arbuzmell CLI can be installed separately without affecting the automation.

---

## 6. Implementation Sequence

1. **Build `plaud_client.py`** — list + details + audio URL, with token resolution from `PLAUD_TOKEN` env var or `config/plaud_token` file
2. **Test manually** — run against live API, verify field names match expectations
3. **Add `main_direct()` to `automation.py`** — keep Gmail path intact
4. **Create `processed_ids.json` state file infrastructure**
5. **Dry-run test** — `PLAUD_MODE=direct python3 -m plaud.src.automation --dry-run`
6. **Run in parallel with Gmail pipeline for 2 weeks** — verify same recordings appear via both paths
7. **Switch entry point** — set `PLAUD_MODE=direct` as default in `run_automation.sh`
8. **After 30 days of stable direct API operation** — disable Gmail polling, update `automation.py` to remove Gmail path

---

## 7. Open Questions

1. **Pagination**: Does `/file/simple/web` return all recordings or just the most recent N? The `skip`+`limit` params suggest full pagination is supported. Test with `limit=50, skip=0` then `skip=50` etc. to confirm.

2. **New recording detection**: The cleanest approach is `sort_by=start_time&is_desc=true` and stop paginating when `start_time < last_run_timestamp`. Confirm that `start_time` in the API response is the recording date (not upload date).

3. **Recordings without AI content**: Plaud takes time to process. Use `has_transcription` and `has_summary` flags. For recordings not yet processed: either skip them (re-check next run) or trigger analysis via `PATCH /file/{id}` + poll. Recommend skip-and-retry for simplicity.

4. **Token lifetime**: Monitor empirically. If token lasts < 2 weeks, the manual refresh burden is high. If > 4 weeks, it's manageable. Consider a Telegram reminder every 25 days as a proactive reminder.
