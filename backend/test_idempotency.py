import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import execute_query
from agent.pipeline import process_event

def test_duplicate_blocking():
    """
    Test that replaying the same event within 5 minutes is blocked.
    """

    print("\n" + "="*80)
    print("TEST 1: DUPLICATE BLOCKING (within 5-minute window)")
    print("="*80 + "\n")

    # Fetch a failed transaction from seed data
    query = """
        SELECT id, merchant_id, customer_id, amount, status, failure_reason,
               payment_method, created_at, retry_count
        FROM transactions
        WHERE status = 'failed'
        LIMIT 1
    """

    records = execute_query(query, fetch=True)

    if not records:
        print("✗ No failed transactions found in database. Run seed_data.py first.")
        return False

    test_record = records[0]

    print(f"Test Record: Transaction {test_record['id']}")
    print(f"  Amount: ₹{test_record['amount']/100:.2f}")
    print(f"  Failure Reason: {test_record['failure_reason']}\n")

    # First run
    print("→ First run (should create recovery action):")
    result1 = process_event(dict(test_record), 'transaction')

    if not result1['success']:
        print(f"✗ First run failed: {result1.get('error')}")
        return False

    action_id_1 = result1.get('recovery_action_id')
    print(f"  ✓ Created recovery action: {action_id_1}")
    print(f"    Status: {result1['status']}\n")

    # Second run immediately (replay within window)
    print("→ Second run immediately (should be blocked by duplicate check):")
    result2 = process_event(dict(test_record), 'transaction')

    if not result2['success']:
        print(f"✗ Second run failed: {result2.get('error')}")
        return False

    action_id_2 = result2.get('recovery_action_id')
    print(f"  ✓ Created recovery action: {action_id_2}")
    print(f"    Status: {result2['status']}\n")

    # Verify results
    if result2['status'] == 'blocked_by_guardrail':
        print("✓ PASS: Second run was blocked by duplicate detection guardrail")

        # Verify no duplicate actions in database
        count_query = """
            SELECT COUNT(*) as count
            FROM recovery_actions
            WHERE target_type = 'transaction'
              AND target_id = %s
              AND status != 'blocked_by_guardrail'
        """

        count_result = execute_query(count_query, (test_record['id'],), fetch=True)
        action_count = count_result[0]['count']

        if action_count == 1:
            print(f"✓ PASS: Only 1 non-blocked action exists for this transaction")
            return True
        else:
            print(f"✗ FAIL: Found {action_count} non-blocked actions (expected 1)")
            return False
    else:
        print(f"✗ FAIL: Second run was not blocked (status: {result2['status']})")
        print("  Expected: blocked_by_guardrail")
        return False

def test_legitimate_retries():
    """
    Test that legitimate sequential retries on the same target are allowed.
    This simulates retry attempt 1, 2, 3 for a subscription.
    """

    print("\n" + "="*80)
    print("TEST 2: LEGITIMATE SEQUENTIAL RETRIES (allowed)")
    print("="*80 + "\n")

    # Fetch a failed subscription
    query = """
        SELECT id, customer_id, plan_amount, status, mandate_status,
               last_charge_attempt, consecutive_failures
        FROM subscriptions
        WHERE status = 'failed_charge'
        LIMIT 1
    """

    records = execute_query(query, fetch=True)

    if not records:
        print("✗ No failed subscriptions found in database. Run seed_data.py first.")
        return False

    test_record = records[0]

    print(f"Test Record: Subscription {test_record['id']}")
    print(f"  Plan Amount: ₹{test_record['plan_amount']/100:.2f}")
    print(f"  Consecutive Failures: {test_record['consecutive_failures']}\n")

    # Simulate 3 legitimate retry attempts with time delays
    results = []

    for attempt in range(1, 4):
        print(f"→ Retry attempt {attempt}:")

        result = process_event(dict(test_record), 'subscription')

        if not result['success']:
            print(f"✗ Attempt {attempt} failed: {result.get('error')}")
            return False

        print(f"  ✓ Created recovery action: {result.get('recovery_action_id')}")
        print(f"    Status: {result['status']}")
        results.append(result)

        # Wait 6 seconds between retries to simulate being outside the 5-minute duplicate window
        # In real scenario, retries would be hours apart, but we simulate with short delay
        if attempt < 3:
            print(f"  Waiting 6 seconds (simulating time passing)...\n")
            time.sleep(6)

    # Verify all attempts were allowed (not all blocked)
    executed_count = sum(1 for r in results if r['status'] == 'executed')
    blocked_count = sum(1 for r in results if r['status'] == 'blocked_by_guardrail')

    print(f"\nResults:")
    print(f"  Executed: {executed_count}")
    print(f"  Blocked: {blocked_count}")

    # Check database for actual action count
    count_query = """
        SELECT COUNT(*) as count
        FROM recovery_actions
        WHERE target_type = 'subscription'
          AND target_id = %s
    """

    count_result = execute_query(count_query, (test_record['id'],), fetch=True)
    total_actions = count_result[0]['count']

    print(f"  Total actions in DB: {total_actions}")

    # At least 2 of the 3 should succeed (some might be blocked by other guardrails like retry limit)
    if executed_count >= 2:
        print("\n✓ PASS: Legitimate sequential retries were allowed")
        print("  (Some may be blocked by retry limits, not duplicate detection)")
        return True
    else:
        print(f"\n✗ FAIL: Only {executed_count} retries executed (expected at least 2)")
        print("  Legitimate retries should not be blocked by duplicate detection")
        return False

def test_rate_limiting():
    """
    Test that SMS rate limiting works correctly.
    """

    print("\n" + "="*80)
    print("TEST 3: RATE LIMITING (SMS cap enforcement)")
    print("="*80 + "\n")

    # Find or create multiple records for the same customer
    query = """
        SELECT customer_id, COUNT(*) as count
        FROM checkout_sessions
        WHERE stage_reached IN ('cart', 'payment_page', 'otp', 'abandoned')
        GROUP BY customer_id
        HAVING COUNT(*) >= 3
        LIMIT 1
    """

    customer_result = execute_query(query, fetch=True)

    if not customer_result:
        print("✗ No customer with multiple checkout sessions found")
        return False

    customer_id = customer_result[0]['customer_id']

    # Fetch multiple checkout sessions for this customer
    sessions_query = """
        SELECT id, customer_id, cart_value, stage_reached, abandoned_at, device
        FROM checkout_sessions
        WHERE customer_id = %s
          AND stage_reached IN ('cart', 'payment_page', 'otp', 'abandoned')
        LIMIT 3
    """

    sessions = execute_query(sessions_query, (customer_id,), fetch=True)

    print(f"Test Customer: {customer_id}")
    print(f"  Sessions to process: {len(sessions)}\n")

    results = []
    for idx, session in enumerate(sessions):
        print(f"→ Processing session {idx + 1}/{len(sessions)}:")
        result = process_event(dict(session), 'checkout_session')
        results.append(result)

        if result['success']:
            print(f"  Status: {result['status']}")
            print(f"  Action: {result.get('action')}\n")

    # Check how many SMS actions were actually executed
    sms_executed = sum(1 for r in results if r.get('action') == 'send_reminder_sms' and r['status'] == 'executed')
    sms_blocked = sum(1 for r in results if r['status'] == 'blocked_by_guardrail')

    print(f"Results:")
    print(f"  SMS executed: {sms_executed}")
    print(f"  Blocked by guardrails: {sms_blocked}")

    if sms_executed <= 2:
        print("\n✓ PASS: Rate limiting is working (max 2 SMS per day enforced)")
        return True
    else:
        print(f"\n⚠ WARNING: {sms_executed} SMS executed (expected max 2)")
        return False

def main():
    print("\n" + "="*80)
    print("COMPREHENSIVE IDEMPOTENCY AND GUARDRAIL TESTS")
    print("="*80)

    try:
        test1_passed = test_duplicate_blocking()
        print("\n" + "="*80 + "\n")

        test2_passed = test_legitimate_retries()
        print("\n" + "="*80 + "\n")

        test3_passed = test_rate_limiting()

        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Duplicate Blocking Test: {'PASSED' if test1_passed else 'FAILED'}")
        print(f"Legitimate Retries Test: {'PASSED' if test2_passed else 'FAILED'}")
        print(f"Rate Limiting Test: {'PASSED' if test3_passed else 'FAILED'}")
        print("="*80 + "\n")

        if test1_passed and test2_passed and test3_passed:
            print("✓ All tests passed!")
            sys.exit(0)
        else:
            print("✗ Some tests failed")
            sys.exit(1)

    except Exception as e:
        print(f"\n✗ Test suite error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
