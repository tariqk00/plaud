import sqlite3, json

c = sqlite3.connect('/DATA/AppData/database.sqlite')
q = "SELECT nodes FROM workflow_entity WHERE name = 'Plaud End-to-End (AI-Powered)'"
res = c.execute(q).fetchone()

if res:
    try:
        nodes = json.loads(res[0])
        print("NODES:")
        for n in nodes:
            print(n['name'] + " (" + n['type'] + ")")
    except Exception as x:
        print(f"Error: {x}")
