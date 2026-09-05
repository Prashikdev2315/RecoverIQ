import sys
sys.stdout.reconfigure(encoding='utf-8')
from database import execute_query

print("=== recovery_actions with timing data ===")
rows = execute_query("""
    SELECT
        ra.id,
        ra.target_type,
        ra.status,
        ra.created_at,
        ra.processed_at,
        ra.processing_duration_seconds,
        CASE
            WHEN ra.target_type = 'transaction' THEN t.created_at
            WHEN ra.target_type = 'checkout_session' THEN cs.abandoned_at
            WHEN ra.target_type = 'subscription' THEN s.last_charge_attempt
        END as source_created_at
    FROM recovery_actions ra
    LEFT JOIN transactions t ON ra.target_type = 'transaction' AND ra.target_id = t.id
    LEFT JOIN checkout_sessions cs ON ra.target_type = 'checkout_session' AND ra.target_id = cs.id
    LEFT JOIN subscriptions s ON ra.target_type = 'subscription' AND ra.target_id = s.id
    ORDER BY ra.created_at DESC
    LIMIT 10
""", fetch=True)

print(f"Total rows: {len(rows)}")
for r in rows:
    print(f"""
  id={str(r['id'])[:8]}  type={r['target_type']}  status={r['status']}
  ra.created_at={r['created_at']}
  ra.processed_at={r['processed_at']}
  processing_duration_seconds={r['processing_duration_seconds']}
  source_created_at={r['source_created_at']}""")

print("\n=== processing_duration_seconds summary ===")
summary = execute_query("""
    SELECT
        COUNT(*) as total,
        COUNT(processing_duration_seconds) as with_duration,
        AVG(processing_duration_seconds) as avg_dur,
        MIN(processing_duration_seconds) as min_dur,
        MAX(processing_duration_seconds) as max_dur
    FROM recovery_actions
""", fetch=True)
s = summary[0]
print(f"  total rows: {s['total']}")
print(f"  rows WITH processing_duration_seconds: {s['with_duration']}")
print(f"  avg: {s['avg_dur']}  min: {s['min_dur']}  max: {s['max_dur']}")
