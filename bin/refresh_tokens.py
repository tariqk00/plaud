
import sys
import os
# Add repo root to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

"""
Interactive console tool to manually refresh Google OAuth tokens 
using the Out-of-Band (OOB) flow.
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

def refresh_gmail():
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']
    print("\n--- Refreshing GMAIL Token (config/token_gmail_plaud.json) ---")
    if os.path.exists('config/token_gmail_plaud.json'):
        # print("Removing old config/token_gmail_plaud.json...")
        pass 
    
    flow = InstalledAppFlow.from_client_secrets_file('config/credentials.json', SCOPES)
    # Try OOB flow
    flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
    
    auth_url, _ = flow.authorization_url(prompt='consent')
    
    print('Please visit this URL to authorize this application: {}'.format(auth_url))
    code = input('Enter the authorization code: ')
    
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    with open('config/token_gmail_plaud.json', 'w') as token:
        token.write(creds.to_json())
    print("Successfully saved config/token_gmail_plaud.json")

def refresh_drive():
    SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.metadata.readonly']
    print("\n--- Refreshing DRIVE Token (config/token_drive_sorter.json) ---")
    if os.path.exists('config/token_drive_sorter.json'):
        # print("Removing old config/token_drive_sorter.json...")
        pass
        
    flow = InstalledAppFlow.from_client_secrets_file('config/credentials.json', SCOPES)
    # Try OOB flow
    flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
    
    auth_url, _ = flow.authorization_url(prompt='consent')
    
    print('Please visit this URL to authorize this application: {}'.format(auth_url))
    code = input('Enter the authorization code: ')
    
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    with open('config/token_drive_sorter.json', 'w') as token:
        token.write(creds.to_json())
    print("Successfully saved config/token_drive_sorter.json")

if __name__ == "__main__":
    print("Please ensure config/credentials.json is present.")
    # refresh_gmail()
    refresh_drive() # Do one at a time to avoid confusion or Timeout
