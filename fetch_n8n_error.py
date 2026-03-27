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
        # Search all string values for "error" or "message" to reconstruct what broke
        errors = []
        messages = []
        for index, item in enumerate(data):
            if isinstance(item, dict):
                if 'message' in item:
                    # look up the pointer
                    ptr = item['message']
                    if str(ptr).isdigit():
                        messages.append(data[int(ptr)])
                
                if 'causeDetailed' in item:
                    ptr = item['causeDetailed']
                    if str(ptr).isdigit():
                        errors.append(data[int(ptr)])

        print(f"STATUS: {res[1]}")
        print(f"MESSAGES: {messages}")
        print(f"CAUSES: {errors}")
        
    except Exception as x:
        print(f"Could not parse json: {x}")
else:
    print("No execution found.")
