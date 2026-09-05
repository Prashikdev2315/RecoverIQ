import sys
sys.stdout.reconfigure(encoding='utf-8')
from database import execute_query

tables = ['transactions', 'checkout_sessions', 'subscriptions', 'recovery_actions', 'hinglish_messages']
for t in tables:
    try:
        r = execute_query(f"SELECT COUNT(*) as cnt FROM {t}", fetch=True)
        print(f"{t}: {r[0]['cnt']} rows")
    except Exception as e:
        print(f"{t}: ERROR - {e}")

# Check if customer_name exists in transactions
try:
    sample = execute_query("SELECT id, customer_name, created_at FROM transactions LIMIT 3", fetch=True)
    print("\nSample transactions with customer_name:")
    for row in sample:
        print(f"  {dict(row)}")
except Exception as e:
    print(f"customer_name check error: {e}")
