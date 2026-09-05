import sys
sys.stdout.reconfigure(encoding='utf-8')
from database import execute_query

# Clear old stale rows (created before fix)
result = execute_query("DELETE FROM recovery_actions RETURNING id", fetch=True)
print(f"Deleted {len(result)} stale recovery_action rows")
