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
        # Find the Gmail Trigger output
        for item in data:
            if isinstance(item, dict) and 'payload' in item:
                payload = data[int(item['payload'])] if str(item['payload']).isdigit() else item['payload']
                print("KEYS IN PAYLOAD:", list(payload.keys()))
                if 'body' in payload:
                    print("BODY KEYS:", list(payload['body'].keys()))
                    if 'size' in payload['body']:
                         print("BODY SIZE:", payload['body']['size'])
                if 'parts' in payload:
                    print("PARTS DETECTED:", len(payload['parts']))
                    for i, p in enumerate(payload['parts']):
                         print(f"  PART {i} MIME:", p.get('mimeType'))
                         if 'body' in p:
                             print(f"  PART {i} BODY SIZE:", p['body'].get('size'))
                break
    except Exception as x:
        print(f"Error: {x}")
