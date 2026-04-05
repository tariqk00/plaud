"""
Main automation workflow for Plaud.ai.
Orchestrates: Gmail Search -> Content Extraction -> Drive Upload -> Email Archiving.
"""
import base64
import datetime
import os
import re
import sys

_toolbox = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "toolbox")
if _toolbox not in sys.path:
    sys.path.insert(0, _toolbox)
from lib.telegram import send_message

from src.mcp_server import gmail as gmail_mcp
from src.mcp_server import drive as drive_mcp

def parse_date_and_subject(date_str, raw_subject):
    # Base date from email date header
    dt = datetime.datetime.now()
    try:
        dt = datetime.datetime.strptime(date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
    except Exception:
        pass
        
    year = dt.strftime("%Y")
    doc_date = dt.strftime("%Y-%m-%d")
    
    # Check for explicit date in subject like 02-13 or 02/13
    match = re.search(r'\b(\d{2})[-/](\d{2})\b', raw_subject)
    if match:
        doc_date = f"{year}-{match.group(1)}-{match.group(2)}"
        
    # Clean subject
    safe_subject = re.sub(r'^(Fwd:\s*|Re:\s*)+', '', raw_subject, flags=re.IGNORECASE)
    safe_subject = re.sub(r'\[plaud.*?\]', '', safe_subject, flags=re.IGNORECASE)
    safe_subject = re.sub(r'\b\d{2}[-/]\d{2}\b', '', safe_subject)
    safe_subject = re.sub(r'[\\/:*?"<>|]', '-', safe_subject)
    safe_subject = safe_subject.strip()
    safe_subject = re.sub(r'^[- \t]+', '', safe_subject).strip()
    
    if not safe_subject:
        safe_subject = "Meeting Recording"
        
    return doc_date, safe_subject

def main():
    print("Starting Plaud.ai Automation...")

    # 1. Search for emails
    emails = gmail_mcp.search_plaud_emails()

    if not emails or (isinstance(emails, list) and len(emails) > 0 and isinstance(emails[0], str) and "error" in emails[0].lower()):
        print(f"Error or no emails found: {emails}")
        return

    if not emails:
        print("No new Plaud.ai emails found.")
        return

    processed = []
    errors = []

    # 2. Get/Create Drive Folder
    folder_id = drive_mcp.get_or_create_folder("01 - Second Brain/Plaud")
    print(f"Target Drive Folder ID (Plaud): {folder_id}")

    for email in emails:
        print(f"Processing email: {email['subject']} ({email['date']})")

        # 3. Get Full Content
        content = gmail_mcp.get_email_content(email['id'])

        if "error" in content:
            print(f"Error fetching content for {email['id']}: {content['error']}")
            errors.append(email['subject'])
            continue
            
        # 4. Extract Date & Clean Subject
        doc_date, safe_subject = parse_date_and_subject(email['date'], email['subject'])
        markdown_filename = f"{doc_date} - {safe_subject}.md"
        
        # 5. Create Markdown Content
        md_body = f"# {safe_subject}\n\n"
        md_body += f"**Date:** {doc_date}\n"
        md_body += f"**From:** PLAUD.AI\n\n"
        md_body += "---\n\n"
        md_body += content['body']
        
        # 6. Upload Markdown to Drive
        print(f"Uploading Markdown: {markdown_filename}")
        drive_mcp.upload_file(markdown_filename, md_body, folder_id)
        
        # 7. Handle Attachments — text/markdown only, skip audio
        text_exts = {'.txt', '.md', '.markdown'}
        for att in content['attachments']:
            att_ext = os.path.splitext(att['filename'])[1].lower()
            if att_ext not in text_exts:
                print(f"Skipping non-text attachment: {att['filename']}")
                continue

            att_filename = f"{doc_date} - {safe_subject} - Transcript.md"
            print(f"Uploading Attachment: {att_filename}")
            att_data = gmail_mcp.download_attachment(email['id'], att['attachmentId'])
            att_text = base64.urlsafe_b64decode(att_data + '==').decode('utf-8', errors='replace')
            drive_mcp.upload_file(att_filename, att_text, folder_id)
            
        # 8. Archive Email
        print(f"Archiving thread: {email['threadId']}")
        gmail_mcp.archive_email_thread(email['threadId'])
        processed.append(f"  {doc_date} — {safe_subject}")

    print("Automation completed successfully.")
    lines = [f"{len(processed)} recording{'s' if len(processed) != 1 else ''} processed"]
    lines.extend(processed)
    if errors:
        lines.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}:")
        lines.extend(f"  Error: {s}" for s in errors)
    send_message("\n".join(lines), service="plaud-automation")

if __name__ == "__main__":
    main()
