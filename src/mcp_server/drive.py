"""
FastMCP Server implementation for Google Drive.
Exposes tools to Create Folders and Upload Files (Text/Binary).
"""
import os.path
import io
import base64
import sys
from typing import Optional, List, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

# Ensure local toolbox package is importable if running script directly
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(current_dir))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from toolbox.lib.google_api import GoogleAuth
from mcp.server.fastmcp import FastMCP

# If modifying these scopes, delete the file config/token_drive.json.
SCOPES = ['https://www.googleapis.com/auth/drive'] # Using full drive scope for consistency with toolbox

mcp = FastMCP("GoogleDrive")

def get_drive_service():
    toolbox_root = os.path.join(os.path.dirname(repo_root), 'toolbox')
    auth = GoogleAuth(base_dir=toolbox_root)
    creds = auth.get_credentials(token_filename='token_drive_sorter.json', scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

@mcp.tool()
def get_or_create_folder(folder_path: str) -> str:
    """
    Get the ID of a folder path (e.g., 'Filing Cabinet/Plaud').
    Creates the folders if they don't exist.
    """
    service = get_drive_service()
    parts = folder_path.strip('/').split('/')
    parent_id = 'root'
    
    for part in parts:
        query = f"name = '{part}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        
        if not files:
            file_metadata = {
                'name': part,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            parent_id = folder.get('id')
        else:
            parent_id = files[0].get('id')
            
    return parent_id

@mcp.tool()
def upload_file(filename: str, content: str, folder_id: str, mime_type: str = 'text/markdown') -> str:
    """
    Upload a text file (like Markdown) to a specific Google Drive folder.
    """
    service = get_drive_service()
    try:
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        fh = io.BytesIO(content.encode())
        media = MediaIoBaseUpload(fh, mimetype=mime_type, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return f"File ID: {file.get('id')}"
    except HttpError as error:
        return f"An error occurred: {error}"

@mcp.tool()
def upload_binary_file(filename: str, base64_content: str, folder_id: str, mime_type: str = 'application/octet-stream') -> str:
    """
    Upload a binary file (from base64 string) to a specific Google Drive folder.
    """
    service = get_drive_service()
    try:
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        file_content = base64.urlsafe_b64decode(base64_content)
        fh = io.BytesIO(file_content)
        media = MediaIoBaseUpload(fh, mimetype=mime_type, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return f"File ID: {file.get('id')}"
    except HttpError as error:
        return f"An error occurred: {error}"

if __name__ == "__main__":
    mcp.run()
