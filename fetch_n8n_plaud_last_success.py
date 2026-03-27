import sqlite3, json

c = sqlite3.connect('/DATA/AppData/database.sqlite')
q = """
SELECT e.id, e.status, d.data
FROM execution_entity e 
JOIN workflow_entity w ON e.workflowId = w.id 
JOIN execution_data d ON e.id = d.executionId 
WHERE w.name = 'Plaud End-to-End (AI-Powered)' 
ORDER BY e.stoppedAt DESC LIMIT 1
"""
res = c.execute(q).fetchone()

if res:
    try:
        data = json.loads(res[2])
        for index, item in enumerate(data):
            if isinstance(item, dict):
                if 'snippet' in item and 'id' in item:
                    # found the gmail node simplified response
                    print("GMAIL KEYS:", list(item.keys()))
                    
                    found_keys = []
                    # Let's see what variables have text in them
                    for k in item.keys():
                        if k in ['text', 'textPlain', 'textHtml', 'textAsHtml', 'html', 'body']:
                            # look up pointer
                            val = data[int(item[k])] if str(item[k]).isdigit() else item[k]
                            print(f"FOUND {k}: {str(val)[:100]}...")
                            found_keys.append(k)
                    
                    if not found_keys:
                        print("No text/body keys found at top level.")
                        # Check payload
                        if 'payload' in item:
                             print("PAYLOAD:", type(data[int(item['payload'])] if str(item['payload']).isdigit() else item['payload']))
    except Exception as x:
        print(f"Could not parse json: {x}")
