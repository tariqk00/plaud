# Plaud.ai to Google Drive Automation (DEPRECATED)

> [!WARNING]
> **DEPRECATED**: This standalone repository is deprecated. All functionality has been migrated to the [toolbox/services/email_extractor](../../toolbox/services/email_extractor) service in the `toolbox` repository.
>
> Please use the unified `email-extractor` service going forward.

Automates processing of Plaud.ai recording emails — saves summaries and attachments to Google Drive and archives the emails from Gmail.

> [!NOTE]
> **Documentation Hub**: See [setup/docs/INDEX.md](../../setup/docs/INDEX.md) for master environment rules.
> Repository rules are in [.agent/rules.md](./.agent/rules.md).

## What It Does

1. Searches Gmail for unread emails from `no-reply@plaud.ai` with `[PLAUD-AutoFlow]` in the subject
2. Converts the email body to a Markdown file named `YYYY-MM-DD - [Subject].md`
3. Downloads any recording/transcript attachments
4. Routes files to Google Drive:
   - Summaries and recordings → `Filing Cabinet/Plaud`
   - Transcripts (`.txt` files) → `Filing Cabinet/Transcripts`
5. Archives the processed email from the Gmail inbox

## Structure

```
src/
  automation.py          # Main orchestration script
  mcp_server/
    gmail.py             # Gmail MCP server (search, download, archive)
    drive.py             # Drive MCP server (folder creation, file upload)
bin/
  run_automation.sh      # Entry point — sets PYTHONPATH and runs automation
  refresh_tokens.py      # Re-authenticate OAuth tokens interactively
  list_files.py          # Diagnostic: list files in Drive Plaud folder
config/
  credentials.json       # OAuth client secrets (gitignored)
  token.json             # Gmail token (gitignored, auto-generated)
test_filename_parsing.py # Unit tests for date/subject parsing
test_real_emails.py      # Integration test against real Gmail
```

## Dependencies

Requires the [toolbox](../toolbox) repo as a sibling directory — uses `toolbox.lib.google_api` for OAuth handling.

Install dependencies:
```bash
pip install -r requirements.txt
```

## Setup

1. Place `credentials.json` (Google Cloud OAuth client secrets) in `config/`
2. Run token setup:
   ```bash
   python3 bin/refresh_tokens.py
   ```
3. Run the automation:
   ```bash
   bash bin/run_automation.sh
   ```

## Scheduling

Runs daily at **7:00 AM** via a systemd user timer on the NUC.

```bash
# Check timer status
systemctl --user list-timers plaud-automation.timer

# Check logs
journalctl --user -u plaud-automation -n 50
```

## License
MIT
