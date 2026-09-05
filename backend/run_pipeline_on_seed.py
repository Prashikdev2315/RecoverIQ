import sys
from datetime import datetime
from database import execute_query
from agent.pipeline import process_event

def fetch_all_records():
    """Fetch all records that need recovery actions."""

    print("Fetching seed data from database...\n")

    # Fetch failed transactions
    transactions_query = """
        SELECT id, merchant_id, customer_id, customer_name, amount, status, failure_reason,
               payment_method, created_at, retry_count
        FROM transactions
        WHERE status = 'failed'
        ORDER BY created_at DESC
    """

    transactions = execute_query(transactions_query, fetch=True)
    print(f"✓ Found {len(transactions)} failed transactions")

    # Fetch abandoned checkout sessions
    checkout_query = """
        SELECT id, customer_id, customer_name, cart_value, stage_reached, abandoned_at, device
        FROM checkout_sessions
        WHERE stage_reached IN ('cart', 'payment_page', 'otp', 'abandoned')
        ORDER BY abandoned_at DESC
    """

    checkouts = execute_query(checkout_query, fetch=True)
    print(f"✓ Found {len(checkouts)} abandoned checkout sessions")

    # Fetch failed subscriptions
    subscriptions_query = """
        SELECT id, customer_id, customer_name, plan_amount, status, mandate_status,
               last_charge_attempt, consecutive_failures
        FROM subscriptions
        WHERE status = 'failed_charge'
        ORDER BY last_charge_attempt DESC
    """

    subscriptions = execute_query(subscriptions_query, fetch=True)
    print(f"✓ Found {len(subscriptions)} failed subscriptions\n")

    return {
        'transactions': transactions,
        'checkouts': checkouts,
        'subscriptions': subscriptions
    }

def run_pipeline_on_all_records(records, limit=None):
    """Run the recovery pipeline on all seed data."""

    total_processed = 0
    total_executed = 0
    total_blocked = 0
    total_skipped = 0
    total_errors = 0

    # Process transactions
    print("="*80)
    print("PROCESSING FAILED TRANSACTIONS")
    print("="*80)

    tx_limit = limit if limit else len(records['transactions'])
    for idx, tx in enumerate(records['transactions'][:tx_limit]):
        result = process_event(tx, 'transaction')
        total_processed += 1

        if result['success']:
            if result['status'] == 'executed':
                total_executed += 1
            elif result['status'] == 'blocked_by_guardrail':
                total_blocked += 1
            elif result['status'] == 'skipped':
                total_skipped += 1
        else:
            total_errors += 1

    # Process checkout sessions
    print("\n" + "="*80)
    print("PROCESSING ABANDONED CHECKOUT SESSIONS")
    print("="*80)

    cs_limit = limit if limit else len(records['checkouts'])
    for idx, cs in enumerate(records['checkouts'][:cs_limit]):
        result = process_event(cs, 'checkout_session')
        total_processed += 1

        if result['success']:
            if result['status'] == 'executed':
                total_executed += 1
            elif result['status'] == 'blocked_by_guardrail':
                total_blocked += 1
            elif result['status'] == 'skipped':
                total_skipped += 1
        else:
            total_errors += 1

    # Process subscriptions
    print("\n" + "="*80)
    print("PROCESSING FAILED SUBSCRIPTIONS")
    print("="*80)

    sub_limit = limit if limit else len(records['subscriptions'])
    for idx, sub in enumerate(records['subscriptions'][:sub_limit]):
        result = process_event(sub, 'subscription')
        total_processed += 1

        if result['success']:
            if result['status'] == 'executed':
                total_executed += 1
            elif result['status'] == 'blocked_by_guardrail':
                total_blocked += 1
            elif result['status'] == 'skipped':
                total_skipped += 1
        else:
            total_errors += 1

    # Summary
    print("\n" + "="*80)
    print("PIPELINE RUN SUMMARY")
    print("="*80)
    print(f"Total records processed: {total_processed}")
    print(f"  ✓ Executed: {total_executed}")
    print(f"  ⚠ Blocked by guardrails: {total_blocked}")
    print(f"  → Skipped: {total_skipped}")
    print(f"  ✗ Errors: {total_errors}")
    print("="*80)

    # Show recovery_actions stats
    stats_query = """
        SELECT status, COUNT(*) as count
        FROM recovery_actions
        GROUP BY status
        ORDER BY count DESC
    """

    stats = execute_query(stats_query, fetch=True)
    print("\nRecovery Actions by Status:")
    for stat in stats:
        print(f"  {stat['status']}: {stat['count']}")

    action_stats_query = """
        SELECT executed_action, COUNT(*) as count
        FROM recovery_actions
        GROUP BY executed_action
        ORDER BY count DESC
    """

    action_stats = execute_query(action_stats_query, fetch=True)
    print("\nRecovery Actions by Type:")
    for stat in action_stats:
        print(f"  {stat['executed_action']}: {stat['count']}")

    print("\n" + "="*80 + "\n")

def main():
    """Main entry point for batch processing."""

    print("\n" + "="*80)
    print("AI REVENUE RECOVERY AGENT - BATCH PIPELINE RUNNER")
    print("="*80)
    print(f"Started at: {datetime.now().isoformat()}\n")

    # Check for limit argument
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            print(f"Processing limit: {limit} records per type\n")
        except ValueError:
            print(f"Invalid limit argument: {sys.argv[1]}, processing all records\n")

    try:
        # Fetch all records
        records = fetch_all_records()

        # Run pipeline
        run_pipeline_on_all_records(records, limit)

        print(f"Completed at: {datetime.now().isoformat()}")
        print("="*80 + "\n")

    except KeyboardInterrupt:
        print("\n\n⚠ Pipeline interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
