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
                
                def print_tree(part, indent=0):
                    prefix = "  " * indent
                    mime = part.get('mimeType', 'unknown')
                    size = part.get('body', {}).get('size', 0)
                    print(f"{prefix}- {mime} (size: {size})")
                    if 'parts' in part:
                        for p in part['parts']:
                            print_tree(p, indent + 1)
                
                print("PAYLOAD TREE:")
                print_tree(payload)
                break
    except Exception as x:
        print(f"Error: {x}")
