# Plaud.ai to Google Drive Automation

This project automates the process of saving Plaud.ai summary emails and their recording attachments to a specific folder in Google Drive.

## Features

- **Gmail Search**: Automatically finds emails from `PLAUD.AI <no-reply@plaud.ai>` with `[PLAUD-AutoFlow]` in the subject.
- **Markdown Conversion**: Saves email content as a Markdown file with the format `YYYY-MM-DD HH:MM [Subject].md`.
- **Attachment Handling**: Saves recording attachments with the same timestamp prefix as the Markdown file.
- **Drive Filing**: Places all files in the `Filing Cabinet/Plaud` directory on Google Drive (creates it if it doesn't exist).
- **Archiving**: Automatically removes processed emails from the Gmail Inbox.

> [!NOTE]
> **Documentation Hub**: See [setup/docs/INDEX.md](../../setup/docs/INDEX.md) for master environment rules.
> Repository rules are located in [.agent/rules.md](./.agent/rules.md).

## Structure

- `gmail_mcp.py`: Gmail MCP server with tools for searching, downloading, and archiving.
- `drive_mcp.py`: Drive MCP server with tools for folder and file management.
- `plaud_automation.py`: The coordination script that runs the automation.

## Setup

1.  **Dependencies**:
    ```bash
    pip install mcp google-api-python-client google-auth-oauthlib google-auth-httplib2
    ```
2.  **Credentials**: Place your Google Cloud `credentials.json` in this directory.
3.  **Run**:
    ```bash
    python3 plaud_automation.py
    ```

## Scheduling

The automation is scheduled to run daily at **7:00 AM** using a systemd user timer.
- `plaud-automation.service`: Defined the execution command.
- `plaud-automation.timer`: Defines the schedule.

To check the timer status:
```bash
systemctl --user list-timers plaud-automation.timer
```

## License
MIT
