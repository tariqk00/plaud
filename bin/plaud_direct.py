"""
Plaud direct API integration.
Runs in parallel with plaud-automation (Gmail-based) during validation period.
Fetches recordings from api.plaud.ai, uploads markdown to Drive.
"""
import datetime
import json
import logging
import os
import re
import sys

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
from toolbox.lib.telegram import send_message

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
    return data.get('data', [])


def get_detail(token: str, file_id: str) -> dict:
    resp = requests.get(f'{DETAIL_URL}/{file_id}', headers=get_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json().get('data', {})


def fetch_transcript(url: str) -> str:
    """Download and parse a transaction JSON transcript into readable text."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    segments = resp.json()
    if not isinstance(segments, list):
        return ''
    lines = []
    for seg in segments:
        speaker = seg.get('speaker', '').strip()
        text = seg.get('text', '').strip()
        if not text:
            continue
        if speaker:
            lines.append(f'**{speaker}:** {text}')
        else:
            lines.append(text)
    return '\n\n'.join(lines)


# ── Filename helpers ─────────────────────────────────────────────────────────

def parse_recording(rec: dict) -> tuple[str, str]:
    """Return (doc_date, safe_subject) from a recording dict."""
    # start_time is ISO or epoch; try ISO first
    raw_time = rec.get('start_time', '')
    doc_date = datetime.date.today().isoformat()
    if raw_time:
        try:
            if isinstance(raw_time, (int, float)):
                dt = datetime.datetime.fromtimestamp(raw_time)
            else:
                dt = datetime.datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
            doc_date = dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    title = rec.get('title', '') or rec.get('file_name', '') or 'Untitled Recording'
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

    # AI summary / meeting minutes from detail
    ai_content = detail.get('ai_content', '') or ''
    if ai_content:
        lines.append('## Summary')
        lines.append('')
        lines.append(ai_content.strip())
        lines.append('')
        lines.append('---')
        lines.append('')

    # Transcript
    transcript_text = ''
    for item in detail.get('content_list', []):
        if item.get('data_type') == 'transaction':
            link = item.get('data_link', '')
            if link and item.get('task_status') in ('done', 'completed', 3, '3'):
                try:
                    transcript_text = fetch_transcript(link)
                except Exception as e:
                    logger.warning(f'Transcript fetch failed for {rec.get("file_id")}: {e}')
            break

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
    last_run = state.get('last_run')

    # Parse last_run cutoff
    cutoff = None
    if last_run:
        try:
            cutoff = datetime.date.fromisoformat(last_run[:10])
        except Exception:
            pass

    recordings = list_recordings(token)
    logger.info(f'Found {len(recordings)} total recordings')

    # Filter: not already processed, and (no cutoff or date >= cutoff - 1 day buffer)
    to_process = []
    for rec in recordings:
        fid = rec.get('file_id') or rec.get('id', '')
        if fid in processed_ids:
            continue
        doc_date, safe_subject = parse_recording(rec)
        if cutoff:
            rec_date = datetime.date.fromisoformat(doc_date)
            if rec_date < cutoff - datetime.timedelta(days=1):
                continue
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
            done.append(f'  {doc_date} — {safe_subject}')
            logger.info(f'Uploaded: {filename}')
        except Exception as e:
            logger.error(f'Failed {fid}: {e}')
            errors.append(f'  {safe_subject}: {e}')

    state['processed_ids'] = list(processed_ids)
    state['last_run'] = datetime.date.today().isoformat()
    save_state(state)

    lines = [f'Plaud Direct: {len(done)} recording{"s" if len(done) != 1 else ""} uploaded']
    lines.extend(done)
    if errors:
        lines.append(f'{len(errors)} error{"s" if len(errors) != 1 else ""}:')
        lines.extend(errors)
    send_message('\n'.join(lines), service='plaud-direct')
    logger.info('Done')


if __name__ == '__main__':
    main()
