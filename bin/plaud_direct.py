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
from toolbox.lib.telegram import send_message, escape

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
    """Download and extract ai_content from a summary JSON."""
    try:
        data = _fetch_gzipped_json(url)
        if isinstance(data, dict):
            return data.get('ai_content', '')
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


# ── Markdown builder ─────────────────────────────────────────────────────────

def build_markdown(rec: dict, detail: dict, doc_date: str, safe_subject: str) -> str:
    lines = [f'# {safe_subject}', '']
    lines.append(f'**Date:** {doc_date}')
    lines.append(f'**Source:** Plaud Direct API')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Collect content by type, preserving order of sum_multi_note entries
    outline_text = ''
    primary_summary = ''
    multi_summaries = []   # list of (tab_name, content)
    transcript_text = ''

    fid = rec.get('file_id') or rec.get('id', '')
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

    # Render sections: Outline → Summary → multi-summaries → Transcript
    if outline_text:
        lines.append('## Outline')
        lines.append('')
        lines.append(outline_text)
        lines.append('')
        lines.append('---')
        lines.append('')

    if primary_summary:
        lines.append('## Summary')
        lines.append('')
        lines.append(primary_summary.strip())
        lines.append('')
        lines.append('---')
        lines.append('')

    for tab_name, content in multi_summaries:
        lines.append(f'## {tab_name}')
        lines.append('')
        lines.append(content.strip())
        lines.append('')
        lines.append('---')
        lines.append('')

    if transcript_text:
        lines.append('## Transcript')
        lines.append('')
        lines.append(transcript_text)
    else:
        lines.append('*(transcript not available)*')

    return '\n'.join(lines)


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
        to_process.append((fid, rec, doc_date, safe_subject))

    logger.info(f'{len(to_process)} new recordings to process')

    if not to_process:
        logger.info('Nothing to process')
        save_state({**state, 'last_run': datetime.date.today().isoformat()})
        return

    folder_id = drive_mcp.get_or_create_folder(DRIVE_FOLDER)
    logger.info(f'Drive folder: {folder_id}')

    done = []
    errors = []

    for fid, rec, doc_date, safe_subject in to_process:
        logger.info(f'Processing: {doc_date} — {safe_subject} ({fid})')
        try:
            detail = get_detail(token, fid)
            md = build_markdown(rec, detail, doc_date, safe_subject)
            filename = f'{doc_date} - {safe_subject}.md'
            drive_mcp.upload_file(filename, md, folder_id)
            processed_ids.add(fid)
            # Save state after each upload so a SIGTERM can't lose progress
            state['processed_ids'] = list(processed_ids)
            state['last_run'] = datetime.date.today().isoformat()
            save_state(state)
            done.append(f'  {doc_date} — {safe_subject}')
            logger.info(f'Uploaded: {filename}')
        except Exception as e:
            logger.error(f'Failed {fid}: {e}')
            errors.append(f'  {safe_subject}: {e}')

    lines = [f'<b>Plaud Direct: {len(done)} recording{"s" if len(done) != 1 else ""} uploaded</b>']
    lines.extend(escape(d) for d in done)
    if errors:
        lines.append(f'{len(errors)} error{"s" if len(errors) != 1 else ""}:')
        lines.extend(escape(e) for e in errors)
    send_message('\n'.join(lines), service='plaud-direct')
    logger.info('Done')


if __name__ == '__main__':
    main()
