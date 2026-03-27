import sqlite3, json

c = sqlite3.connect('/DATA/AppData/database.sqlite')
q = """
SELECT d.data
FROM execution_entity e 
JOIN workflow_entity w ON e.workflowId = w.id 
JOIN execution_data d ON e.id = d.executionId 
WHERE w.name = 'Plaud End-to-End (AI-Powered)' 
ORDER BY e.stoppedAt DESC LIMIT 1
"""
res = c.execute(q).fetchone()

if res:
    try:
        data = json.loads(res[0])
        for item in data:
            if isinstance(item, dict):
                # Is it direct?
                if 'Subject' in item:
                    print(f"Direct Subject: {item.get('Subject')}")
                if 'subject' in item:
                    print(f"Direct subject: {item.get('subject')}")
                
                # Is it in payload.headers?
                if 'payload' in item:
                    payload = data[int(item['payload'])] if str(item['payload']).isdigit() else item['payload']
                    if 'headers' in payload:
                        headers = payload['headers']
                        for h in headers:
                            if h['name'].lower() == 'subject':
                                print(f"Header Subject: {h['value']}")
                                break
                break
    except Exception as x:
        print(f"Error: {x}")
else:
    print("No execution found.")
