"""
FastMCP Server implementation for Gmail.
Exposes tools to Search Emails, Get Content, Download Attachments, and Archive Threads.
"""
import os.path
import base64
from typing import Optional, List, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import sys

# Ensure local toolbox package is importable if running script directly
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(current_dir))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from toolbox.lib.google_api import GoogleAuth
from mcp.server.fastmcp import FastMCP

# If modifying these scopes, delete the file config/token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']

mcp = FastMCP("Gmail")

def get_gmail_service():
    auth = GoogleAuth(base_dir=repo_root)
    creds = auth.get_credentials(token_filename='token.json', credentials_filename='config/credentials.json', scopes=SCOPES)
    return build('gmail', 'v1', credentials=creds)

@mcp.tool()
def search_plaud_emails(query: str = 'from:no-reply@plaud.ai subject:[PLAUD-AutoFlow] in:inbox') -> List[Dict[str, str]]:
    """
    Search for Plaud.ai emails matching the specific criteria.
    Returns a list of email metadata (id, threadId, subject, date).
    Paginates through all results using nextPageToken so no emails are missed.
    """
    service = get_gmail_service()
    try:
        messages = []
        page_token = None
        while True:
            params = {'userId': 'me', 'q': query}
            if page_token:
                params['pageToken'] = page_token
            results = service.users().messages().list(**params).execute()
            messages.extend(results.get('messages', []))
            page_token = results.get('nextPageToken')
            if not page_token:
                break

        email_list = []
        for msg in messages:
            msg_details = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_details['payload']['headers']
            subject = next(h['value'] for h in headers if h['name'] == 'Subject')
            date = next(h['value'] for h in headers if h['name'] == 'Date')
            email_list.append({
                'id': msg['id'],
                'threadId': msg['threadId'],
                'subject': subject,
                'date': date
            })
        return email_list
    except HttpError as error:
        return [f"An error occurred: {error}"]

@mcp.tool()
def get_email_content(message_id: str) -> Dict[str, Any]:
    """
    Retrieve the full content of an email, including body and attachment metadata.
    """
    service = get_gmail_service()
    try:
        message = service.users().messages().get(userId='me', id=message_id).execute()
        payload = message['payload']
        headers = payload['headers']
        
        parts = payload.get('parts', [])
        body = ""
        attachments = []
        
        def process_parts(parts):
            nonlocal body
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode()
                elif part['mimeType'] == 'text/html' and not body:
                     data = part['body'].get('data')
                     if data:
                        # We might want to convert HTML to Markdown later
                        body += base64.urlsafe_b64decode(data).decode()
                elif part.get('parts'):
                    process_parts(part['parts'])
                
                if part.get('filename'):
                    attachments.append({
                        'filename': part['filename'],
                        'attachmentId': part['body'].get('attachmentId'),
                        'size': part['body'].get('size')
                    })

        if not parts:
            data = payload['body'].get('data')
            if data:
                body = base64.urlsafe_b64decode(data).decode()
        else:
            process_parts(parts)
            
        return {
            'body': body,
            'attachments': attachments,
            'subject': next(h['value'] for h in headers if h['name'] == 'Subject'),
            'date': next(h['value'] for h in headers if h['name'] == 'Date')
        }
    except HttpError as error:
        return {"error": str(error)}

@mcp.tool()
def download_attachment(message_id: str, attachment_id: str) -> str:
    """
    Download an attachment by ID and return the base64 encoded content.
    """
    service = get_gmail_service()
    try:
        attachment = service.users().messages().attachments().get(
            userId='me', messageId=message_id, id=attachment_id).execute()
        return attachment['data']
    except HttpError as error:
        return f"An error occurred: {error}"

@mcp.tool()
def archive_email_thread(thread_id: str):
    """
    Archive a specific email thread: remove INBOX label and mark as read.
    Marking as read is the dedup mechanism for emails that bypass INBOX (CATEGORY_UPDATES).
    """
    service = get_gmail_service()
    try:
        service.users().threads().modify(
            userId='me', id=thread_id,
            body={'removeLabelIds': ['INBOX', 'UNREAD']}
        ).execute()
        return f"Thread {thread_id} archived successfully."
    except HttpError as error:
        return f"An error occurred: {error}"

if __name__ == "__main__":
    mcp.run()
