import sys
import datetime
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.automation import parse_date_and_subject

def test_parsing():
    test_cases = [
        {
            "date": "Sat, 07 Mar 2026 15:45:00 +0000",
            "subject": "[Plaud-AutoFlow] 03/07 Team Sync"
        },
        {
            "date": "Fri, 06 Mar 2026 10:20:00 +0000",
            "subject": "Fwd: [Plaud AI] 03-05 Important Client Meeting"
        },
        {
            "date": "Thu, 05 Mar 2026 09:00:00 +0000",
            "subject": "12-31 Year End Review"
        },
        {
            "date": "Wed, 04 Mar 2026 14:30:00 +0000",
            "subject": "Re: Fwd: Plaud Note - Quick sync"
        },
        {
            "date": "Tue, 03 Mar 2026 11:15:00 +0000",
            "subject": "02-28 Project Alpha Kickoff / Planning"
        }
    ]

    print(f"{'Original Subject':<50} | {'Expected Filename (Markdown)':<50}")
    print("-" * 105)
    for tc in test_cases:
        doc_date, safe_subject = parse_date_and_subject(tc["date"], tc["subject"])
        md_filename = f"{doc_date} - {safe_subject}.md"
        print(f"{tc['subject']:<50} | {md_filename:<50}")

if __name__ == "__main__":
    test_parsing()
