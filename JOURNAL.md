# Plaud Automation Journal

## 2026-03-27
- fix: resolved undefined `repo_root` crash in `src/mcp_server/drive.py` — Drive MCP server would fail on startup
- fix: removed unused legacy imports (`Request`, `Credentials`, `InstalledAppFlow`) from `gmail.py` and `drive.py`
- fix: replaced hardcoded absolute `sys.path` entries in `test_filename_parsing.py` and `test_real_emails.py` with relative paths so tests run on any machine
- chore: deleted 10 AI-generated n8n debug scripts (`fetch_*.py`, `analyze_gmail_payload.py`) — these queried the n8n sqlite database for the old "Plaud End-to-End" workflow and have no relation to the Python automation
