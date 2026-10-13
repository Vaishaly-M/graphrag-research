"""Read-only diagnostic of this configured user's active graph transactions."""
import sys,json,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from src.graph import Graph
out=Path(__file__).parent
g=Graph()
try:
 rows=g.query("SHOW TRANSACTIONS YIELD transactionId, username, currentQuery, elapsedTime, status WHERE username = $user RETURN transactionId, currentQuery, toString(elapsedTime) AS elapsed, status",user=os.environ['NEO4J_USERNAME'])
 (out/'active_query_diagnostic.json').write_text(json.dumps(rows,indent=2,default=str)+'\n')
 print(json.dumps(rows,indent=2,default=str))
finally: g.close()
