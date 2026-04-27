"""
Plaud direct API integration.
Fetches recordings from api.plaud.ai, uploads markdown to Drive.
Replaces plaud-automation (Gmail-based pipeline).
"""
import datetime
import json
import logging
import os
import re
import sys

import gzip

import requests

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLAUD_ROOT = os.path.dirname(SCRIPT_DIR)
TOOLBOX_ROOT = os.path.join(os.path.dirname(PLAUD_ROOT), 'toolbox')
PARENT_DIR = os.path.dirname(PLAUD_ROOT)

for p in (PLAUD_ROOT, PARENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.mcp_server import drive as drive_mcp
from toolbox.lib.telegram import send_message, escape, drive_folder_link, monit_link

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('PlaudDirect')

# Paths
TOKEN_FILE = os.path.join(PLAUD_ROOT, 'config', 'plaud_token')
STATE_FILE = os.path.join(PLAUD_ROOT, 'config', 'plaud_api_state.json')

# Plaud API
API_BASE = 'https://api.plaud.ai'
LIST_URL = f'{API_BASE}/file/simple/web'
DETAIL_URL = f'{API_BASE}/file/detail'

# Drive target
DRIVE_FOLDER = '01 - Second Brain/Plaud'

# Max characters for the title portion of a Drive filename, keeping the
# full "YYYY-MM-DD - <title>.md" pattern visible in Drive list view.
MAX_SUBJECT_LEN = 80

TASKS_LIST_NAME = 'Plaud'

EXTRACT_PROMPT = """\
You are extracting actionables from a voice recording.

Recording: {title}
Date: {date_str}

Outline:
{outline}

Summary:
{summary}

Return ONLY valid JSON, no other text:
{{
  "action_items": [{{"text": "...", "due_date": "YYYY-MM-DD or null", "context": "..."}}],
  "decisions": ["..."]
}}

Rules:
- action_items: concrete tasks with a clear owner or commitment (explicit follow-ups, things to do)
- decisions: key conclusions or choices made during the recording
- due_date: parse if explicitly mentioned (e.g. "by Friday" → date), null otherwise
- context: one sentence explaining the task, or null
- Return empty arrays if nothing actionable is found
"""


# ── State management ─────────────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'processed_ids': [], 'last_run': None}


def save_state(state: dict):
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    os.rename(tmp, STATE_FILE)


# ── Plaud API ────────────────────────────────────────────────────────────────

def load_token() -> str:
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(
            f'Plaud token not found at {TOKEN_FILE}\n'
            'Get it from web.plaud.ai → DevTools → Application → Local Storage → tokenstr'
        )
    return open(TOKEN_FILE).read().strip()


def get_headers(token: str) -> dict:
    return {'Authorization': f'bearer {token}', 'Content-Type': 'application/json'}


def list_recordings(token: str) -> list[dict]:
    """Fetch all recordings, newest first."""
    resp = requests.get(
        LIST_URL,
        params={'skip': 0, 'limit': 99999, 'is_trash': 2, 'sort_by': 'start_time', 'is_desc': 'true'},
        headers=get_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get('data_file_list', [])


def get_detail(token: str, file_id: str) -> dict:
    resp = requests.get(f'{DETAIL_URL}/{file_id}', headers=get_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json().get('data', {})


def _fetch_gzipped_json(url: str):
    """Fetch a URL that returns gzip-compressed JSON."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.content
    try:
        data = gzip.decompress(data)
    except OSError:
        pass  # not gzipped
    return json.loads(data)


def fetch_transcript(url: str) -> str:
    """Download and parse a transcript JSON into readable text."""
    segments = _fetch_gzipped_json(url)
    if not isinstance(segments, list):
        return ''
    lines = []
    for seg in segments:
        speaker = (seg.get('speaker') or '').strip()
        text = (seg.get('content') or seg.get('text') or '').strip()
        if not text:
            continue
        if speaker:
            lines.append(f'**{speaker}:** {text}')
        else:
            lines.append(text)
    return '\n\n'.join(lines)


def fetch_summary(url: str) -> str:
    """Download and extract ai_content from a summary JSON.
    Strips embedded image tags (AWS S3 URLs) and leading H1 (repeats title).
    """
    try:
        data = _fetch_gzipped_json(url)
        if isinstance(data, dict):
            content = data.get('ai_content', '')
            # Strip image tags — S3 signed URLs are huge and not useful in Drive
            content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
            # Strip leading H1 — we already have the title as the document H1
            content = re.sub(r'^#[^\n]*\n', '', content.lstrip())
            return content.strip()
    except Exception:
        pass
    return ''


def fetch_outline(url: str) -> str:
    """Download and parse an outline JSON into a topic bullet list."""
    try:
        items = _fetch_gzipped_json(url)
        if isinstance(items, list):
            return '\n'.join(f'- {item["topic"]}' for item in items if item.get('topic'))
    except Exception:
        pass
    return ''


# ── Filename helpers ─────────────────────────────────────────────────────────

def parse_recording(rec: dict) -> tuple[str, str]:
    """Return (doc_date, safe_subject) from a recording dict."""
    # start_time is ISO or epoch; try ISO first
    raw_time = rec.get('start_time', '')
    doc_date = datetime.date.today().isoformat()
    if raw_time:
        try:
            if isinstance(raw_time, (int, float)):
                if raw_time > 1e10:  # milliseconds → seconds
                    raw_time /= 1000
                dt = datetime.datetime.fromtimestamp(raw_time)
            else:
                dt = datetime.datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
            doc_date = dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    title = rec.get('filename', '') or rec.get('title', '') or rec.get('file_name', '') or 'Untitled Recording'
    safe = re.sub(r'[\\/:*?"<>|]', '-', title).strip()
    safe = re.sub(r'\s+', ' ', safe).strip()
    if not safe:
        safe = 'Untitled Recording'
    return doc_date, safe


# ── Content fetcher ───────────────────────────────────────────────────────────

def fetch_content(detail: dict, fid: str) -> dict:
    """Fetch all content types for a recording. Returns dict with all sections."""
    outline_text = ''
    primary_summary = ''
    multi_summaries = []
    transcript_text = ''

    for item in detail.get('content_list', []):
        dtype = item.get('data_type', '')
        link = item.get('data_link', '')
        status = item.get('task_status')
        if not link or status in (None, 0):
            continue
        if dtype == 'outline' and not outline_text:
            try:
                outline_text = fetch_outline(link)
            except Exception as e:
                logger.warning(f'Outline fetch failed for {fid}: {e}')
        elif dtype == 'auto_sum_note' and not primary_summary:
            try:
                primary_summary = fetch_summary(link)
            except Exception as e:
                logger.warning(f'Summary fetch failed for {fid}: {e}')
        elif dtype == 'sum_multi_note':
            tab_name = item.get('data_tab_name') or 'Summary'
            try:
                content = fetch_summary(link)
                if content:
                    multi_summaries.append((tab_name, content))
            except Exception as e:
                logger.warning(f'Multi-summary ({tab_name}) fetch failed for {fid}: {e}')
        elif dtype == 'transaction' and not transcript_text:
            try:
                transcript_text = fetch_transcript(link)
            except Exception as e:
                logger.warning(f'Transcript fetch failed for {fid}: {e}')
        # transaction_polish skipped — redundant with transcript

    return {
        'outline': outline_text,
        'summary': primary_summary,
        'multi_summaries': multi_summaries,
        'transcript': transcript_text,
    }


# ── Markdown builder ─────────────────────────────────────────────────────────

def build_markdown(rec: dict, content: dict, doc_date: str, safe_subject: str) -> str:
    lines = [f'# {safe_subject}', '']
    lines.append(f'**Date:** {doc_date}')
    lines.append(f'**Source:** Plaud Direct API')
    lines.append('')
    lines.append('---')
    lines.append('')

    if content['outline']:
        lines.append('## Outline')
        lines.append('')
        lines.append(content['outline'])
        lines.append('')
        lines.append('---')
        lines.append('')

    if content['summary']:
        lines.append('## Summary')
        lines.append('')
        lines.append(content['summary'].strip())
        lines.append('')
        lines.append('---')
        lines.append('')

    for tab_name, tab_content in content['multi_summaries']:
        lines.append(f'## {tab_name}')
        lines.append('')
        lines.append(tab_content.strip())
        lines.append('')
        lines.append('---')
        lines.append('')

    if content['transcript']:
        lines.append('## Transcript')
        lines.append('')
        lines.append(content['transcript'])
    else:
        lines.append('*(transcript not available)*')

    return '\n'.join(lines)


# ── Action item extraction ────────────────────────────────────────────────────

def extract_actionables(title: str, date_str: str, content: dict) -> dict:
    """
    Run Groq extraction on outline + summary.
    Returns {'action_items': [{text, due_date, context}], 'decisions': [str]}.
    Falls back to empty on any error — never blocks upload.
    """
    outline = content.get('outline', '')
    summary = content.get('summary', '')
    if not outline and not summary:
        return {'action_items': [], 'decisions': []}

    try:
        from toolbox.lib.llm import call_json
        prompt = EXTRACT_PROMPT.format(
            title=title,
            date_str=date_str,
            outline=outline or '(none)',
            summary=summary[:3000] if summary else '(none)',
        )
        result = call_json(prompt)
        if not isinstance(result, dict):
            return {'action_items': [], 'decisions': []}
        action_items = [
            a for a in result.get('action_items', [])
            if isinstance(a, dict) and a.get('text')
        ]
        decisions = [d for d in result.get('decisions', []) if isinstance(d, str) and d]
        return {'action_items': action_items, 'decisions': decisions}
    except Exception as e:
        logger.warning(f'Actionable extraction failed for "{title}": {e}')
        return {'action_items': [], 'decisions': []}


# ── Google Tasks push ─────────────────────────────────────────────────────────

def push_plaud_tasks(items: list, title: str, date_str: str) -> int:
    """Push action items to Google Tasks 'Plaud' list. Returns count created."""
    if not items:
        return 0
    try:
        from toolbox.lib.tasks import get_tasks_service, get_or_create_list
        from toolbox.lib.task_utils import create_unique_tasks
        service = get_tasks_service()
        list_id = get_or_create_list(service, TASKS_LIST_NAME)

        def notes_for(item: dict) -> str:
            notes_parts = []
            if item.get('context'):
                notes_parts.append(item['context'].strip())
            notes_parts.append(f'From: {title} ({date_str})')
            return '\n'.join(notes_parts)

        return create_unique_tasks(
            service,
            list_id,
            items,
            title_fn=lambda item: item.get('text', '').strip(),
            due_fn=lambda item: item.get('due_date') or None,
            notes_fn=notes_for,
        )
    except Exception as e:
        logger.error(f'Plaud Tasks push failed: {e}')
        return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info('Plaud Direct: starting')
    token = load_token()
    state = load_state()
    processed_ids: set[str] = set(state.get('processed_ids', []))

    recordings = list_recordings(token)
    logger.info(f'Found {len(recordings)} total recordings')

    # Filter: skip already-processed and untitled recordings.
    # Untitled recordings are still being processed by Plaud; they'll be
    # picked up on a future run once they have a title.
    to_process = []
    for rec in recordings:
        fid = rec.get('file_id') or rec.get('id', '')
        if fid in processed_ids:
            continue
        raw_title = rec.get('filename', '') or rec.get('title', '') or rec.get('file_name', '')
        if not raw_title:
            continue
        doc_date, safe_subject = parse_recording(rec)
        if len(safe_subject) > MAX_SUBJECT_LEN:
            safe_subject = safe_subject[:MAX_SUBJECT_LEN].rstrip() + '…'
        to_process.append((fid, rec, doc_date, safe_subject))

    logger.info(f'{len(to_process)} new recordings to process')

    if not to_process:
        logger.info('Nothing to process')
        save_state({**state, 'last_run': datetime.date.today().isoformat()})
        return

    folder_id = drive_mcp.get_or_create_folder(DRIVE_FOLDER)
    logger.info(f'Drive folder: {folder_id}')

    done = []   # list of (doc_date, safe_subject, actionables, tasks_created)
    errors = []

    for fid, rec, doc_date, safe_subject in to_process:
        logger.info(f'Processing: {doc_date} — {safe_subject} ({fid})')
        try:
            detail = get_detail(token, fid)
            content = fetch_content(detail, fid)
            md = build_markdown(rec, content, doc_date, safe_subject)
            filename = f'{doc_date} - {safe_subject}.md'
            drive_mcp.upload_file(filename, md, folder_id)
            processed_ids.add(fid)
            # Save state after each upload so a SIGTERM can't lose progress
            state['processed_ids'] = list(processed_ids)
            state['last_run'] = datetime.date.today().isoformat()
            save_state(state)
            logger.info(f'Uploaded: {filename}')

            actionables = extract_actionables(safe_subject, doc_date, content)
            tasks_created = push_plaud_tasks(
                actionables.get('action_items', []), safe_subject, doc_date,
            )
            if tasks_created:
                logger.info(f'Created {tasks_created} task(s) from: {safe_subject}')

            done.append((doc_date, safe_subject, actionables, tasks_created))
        except Exception as e:
            logger.error(f'Failed {fid}: {e}')
            errors.append(f'  {safe_subject}: {e}')

    # Build Telegram message
    total_tasks = sum(t for _, _, _, t in done)
    header = f'<b>Plaud Direct: {len(done)} recording{"s" if len(done) != 1 else ""} uploaded'
    if total_tasks:
        header += f', {total_tasks} task{"s" if total_tasks != 1 else ""} created'
    header += f'</b>  {drive_folder_link(folder_id, "Open folder")}'

    lines = [header]
    for doc_date, safe_subject, actionables, tasks_created in done:
        action_items = actionables.get('action_items', [])
        task_label = f' ({tasks_created} task{"s" if tasks_created != 1 else ""})' if tasks_created else ''
        lines.append(escape(f'  {doc_date} — {safe_subject}{task_label}'))
        for item in action_items:
            due = f' [due: {item["due_date"]}]' if item.get('due_date') else ''
            lines.append(escape(f'    → {item["text"]}{due}'))
        if not action_items:
            lines.append('    <i>(no actionables)</i>')

    if errors:
        lines.append(f'\n<b>{len(errors)} error{"s" if len(errors) != 1 else ""}:</b>')
        lines.extend(escape(e) for e in errors)
        lines.append(f'  {monit_link("Check Monit")} · <code>journalctl --user -u plaud-direct -n 50</code>')

    send_message('\n'.join(lines), service='plaud-direct')
    logger.info('Done')


if __name__ == '__main__':
    main()
