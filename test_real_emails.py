import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.mcp_server import gmail as gmail_mcp
from src.automation import parse_date_and_subject

def main():
    print("Fetching last 5 Plaud emails from Gmail...")
    query = "from:no-reply@plaud.ai"
    emails = gmail_mcp.search_plaud_emails(query=query)
    
    if not emails or (isinstance(emails, list) and len(emails) > 0 and isinstance(emails[0], str) and "error" in emails[0].lower()):
        print(f"Error fetching emails: {emails}")
        return
        
    if not emails:
        print("No plaud emails found in inbox.")
        return
        
    print("\n" + "-" * 105)
    print(f"{'Actual Gmail Subject':<50} | {'Expected Clean Filename':<50}")
    print("-" * 105)
    
    for email in emails[:5]:
        doc_date, safe_subject = parse_date_and_subject(email['date'], email['subject'])
        md_filename = f"{doc_date} - {safe_subject}.md"
        print(f"{email['subject'].strip():<50} | {md_filename:<50}")

if __name__ == '__main__':
    main()
