import os
import random
from datetime import datetime, timedelta
from uuid import uuid4
from dotenv import load_dotenv
from database import get_connection

load_dotenv()

# Generate consistent UUIDs for merchants and customers
MERCHANT_IDS = [str(uuid4()) for _ in range(5)]
CUSTOMER_IDS = [str(uuid4()) for _ in range(100)]

FAILURE_REASONS = {
    'insufficient_funds': 0.35,
    'bank_declined': 0.30,
    'gateway_timeout': 0.15,
    'card_expired': 0.10,
    'invalid_cvv': 0.05,
    'network_error': 0.05
}

PAYMENT_METHODS = ['card', 'upi', 'netbanking', 'wallet']
DEVICES = ['mobile', 'desktop']
CHECKOUT_STAGES = ['cart', 'payment_page', 'otp', 'abandoned', 'completed']

def weighted_choice(choices_dict):
    choices = list(choices_dict.keys())
    weights = list(choices_dict.values())
    return random.choices(choices, weights=weights)[0]

def generate_transactions(conn, count=200):
    cursor = conn.cursor()

    transactions = []

    # Generate mostly failed transactions for recovery scenarios
    for i in range(count):
        merchant_id = random.choice(MERCHANT_IDS)
        customer_id = random.choice(CUSTOMER_IDS)
        amount = random.randint(10000, 500000)

        # 60% failed, 30% success, 10% pending
        status_roll = random.random()
        if status_roll < 0.6:
            status = 'failed'
            failure_reason = weighted_choice(FAILURE_REASONS)
        elif status_roll < 0.9:
            status = 'success'
            failure_reason = None
        else:
            status = 'pending'
            failure_reason = None

        payment_method = random.choice(PAYMENT_METHODS)
        created_at = datetime.now() - timedelta(days=random.randint(0, 30))
        retry_count = random.randint(0, 3) if status == 'failed' else 0

        transactions.append((
            merchant_id, customer_id, amount, status, failure_reason,
            payment_method, created_at, retry_count
        ))

    # Insert hard cases - multiple failures with different reasons
    hard_case_customer = random.choice(CUSTOMER_IDS)
    base_time = datetime.now() - timedelta(days=2)

    # Hard case 1: Card failed 3 times with different reasons
    for idx, reason in enumerate(['card_expired', 'insufficient_funds', 'invalid_cvv']):
        transactions.append((
            random.choice(MERCHANT_IDS),
            hard_case_customer,
            50000,
            'failed',
            reason,
            'card',
            base_time + timedelta(hours=idx * 6),
            idx + 1
        ))

    # Hard case 2: UPI timeout then bank decline
    hard_case_customer2 = random.choice(CUSTOMER_IDS)
    for idx, reason in enumerate(['gateway_timeout', 'bank_declined']):
        transactions.append((
            random.choice(MERCHANT_IDS),
            hard_case_customer2,
            25000,
            'failed',
            reason,
            'upi',
            base_time + timedelta(hours=idx * 3),
            idx + 1
        ))

    # Hard case 3: High-value transaction with network errors
    hard_case_customer3 = random.choice(CUSTOMER_IDS)
    for idx in range(3):
        transactions.append((
            random.choice(MERCHANT_IDS),
            hard_case_customer3,
            200000,
            'failed',
            'network_error',
            'netbanking',
            base_time + timedelta(hours=idx * 12),
            idx + 1
        ))

    # Edge case: Malformed record - missing failure_reason for failed transaction
    # This will be handled gracefully by the system
    transactions.append((
        random.choice(MERCHANT_IDS),
        random.choice(CUSTOMER_IDS),
        15000,
        'failed',
        None,  # Missing failure reason - edge case
        'card',
        datetime.now() - timedelta(days=1),
        1
    ))

    # Edge case: Boundary amounts
    edge_customer = random.choice(CUSTOMER_IDS)

    # Zero amount (should be rejected or handled specially)
    transactions.append((
        random.choice(MERCHANT_IDS),
        edge_customer,
        0,  # Zero amount edge case
        'failed',
        'insufficient_funds',
        'upi',
        datetime.now() - timedelta(hours=1),
        0
    ))

    # Negative amount (should be rejected)
    transactions.append((
        random.choice(MERCHANT_IDS),
        edge_customer,
        -5000,  # Negative amount edge case
        'failed',
        'bank_declined',
        'card',
        datetime.now() - timedelta(hours=2),
        0
    ))

    # Very large amount (1 crore)
    transactions.append((
        random.choice(MERCHANT_IDS),
        edge_customer,
        10000000,  # 1 crore - very large amount edge case
        'failed',
        'bank_declined',
        'netbanking',
        datetime.now() - timedelta(hours=3),
        1
    ))

    # Bulk insert
    cursor.executemany(
        """
        INSERT INTO transactions
        (merchant_id, customer_id, amount, status, failure_reason, payment_method, created_at, retry_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        transactions
    )

    print(f"✓ Generated {len(transactions)} transactions (including {9} hard cases and 1 edge case)")

def generate_checkout_sessions(conn, count=80):
    cursor = conn.cursor()

    sessions = []

    for _ in range(count):
        customer_id = random.choice(CUSTOMER_IDS)
        cart_value = random.randint(5000, 300000)

        # 40% abandoned, 50% completed, 10% in-progress
        stage_roll = random.random()
        if stage_roll < 0.4:
            stage_reached = 'abandoned'
            abandoned_at = datetime.now() - timedelta(hours=random.randint(1, 72))
        elif stage_roll < 0.5:
            stage_reached = random.choice(['cart', 'payment_page', 'otp'])
            abandoned_at = datetime.now() - timedelta(minutes=random.randint(5, 120))
        else:
            stage_reached = 'completed'
            abandoned_at = None

        device = random.choice(DEVICES)

        sessions.append((
            customer_id, cart_value, stage_reached, abandoned_at, device
        ))

    # Hard cases for checkout abandonment
    hard_customer = random.choice(CUSTOMER_IDS)

    # Hard case 1: Abandoned at OTP stage (high intent)
    sessions.append((
        hard_customer,
        75000,
        'otp',
        datetime.now() - timedelta(hours=2),
        'mobile'
    ))

    # Hard case 2: Multiple cart abandonments
    for _ in range(3):
        sessions.append((
            hard_customer,
            random.randint(30000, 100000),
            'cart',
            datetime.now() - timedelta(hours=random.randint(12, 48)),
            'mobile'
        ))

    # Hard case 3: High-value abandoned at payment page
    sessions.append((
        random.choice(CUSTOMER_IDS),
        250000,
        'payment_page',
        datetime.now() - timedelta(hours=6),
        'desktop'
    ))

    # Edge case: Inconsistent state - stage='completed' but abandoned_at is set
    sessions.append((
        random.choice(CUSTOMER_IDS),
        35000,
        'completed',  # Completed but has abandoned_at - inconsistent
        datetime.now() - timedelta(hours=1),
        'mobile'
    ))

    # Edge case: Abandoned at 'abandoned' stage (redundant/unclear)
    sessions.append((
        random.choice(CUSTOMER_IDS),
        12000,
        'abandoned',
        datetime.now() - timedelta(hours=24),
        'desktop'
    ))

    cursor.executemany(
        """
        INSERT INTO checkout_sessions
        (customer_id, cart_value, stage_reached, abandoned_at, device)
        VALUES (%s, %s, %s, %s, %s)
        """,
        sessions
    )

    print(f"✓ Generated {len(sessions)} checkout sessions (including {5} hard cases)")

def generate_subscriptions(conn, count=50):
    cursor = conn.cursor()

    subscriptions = []

    for _ in range(count):
        customer_id = random.choice(CUSTOMER_IDS)
        plan_amount = random.choice([29900, 49900, 99900, 199900])  # Common subscription prices

        # 30% failed_charge, 60% active, 10% other
        status_roll = random.random()
        if status_roll < 0.3:
            status = 'failed_charge'
            consecutive_failures = random.randint(1, 4)
        elif status_roll < 0.9:
            status = 'active'
            consecutive_failures = 0
        else:
            status = random.choice(['paused', 'cancelled'])
            consecutive_failures = 0

        mandate_status_roll = random.random()
        if status == 'failed_charge' and mandate_status_roll < 0.2:
            mandate_status = 'revoked'
        elif mandate_status_roll < 0.1:
            mandate_status = 'pending'
        else:
            mandate_status = 'active'

        last_charge_attempt = datetime.now() - timedelta(days=random.randint(0, 30))

        subscriptions.append((
            customer_id, plan_amount, status, mandate_status,
            last_charge_attempt, consecutive_failures
        ))

    # Hard cases for subscription recovery
    hard_sub_customer = random.choice(CUSTOMER_IDS)

    # Hard case 1: Multiple consecutive failures with active mandate
    subscriptions.append((
        hard_sub_customer,
        99900,
        'failed_charge',
        'active',
        datetime.now() - timedelta(hours=12),
        3
    ))

    # Hard case 2: Failed charge with revoked mandate
    subscriptions.append((
        random.choice(CUSTOMER_IDS),
        49900,
        'failed_charge',
        'revoked',
        datetime.now() - timedelta(days=2),
        2
    ))

    # Hard case 3: High-value subscription with pending mandate
    subscriptions.append((
        random.choice(CUSTOMER_IDS),
        199900,
        'failed_charge',
        'pending',
        datetime.now() - timedelta(hours=24),
        1
    ))

    # Edge case: NULL mandate_status (should trigger defense-in-depth)
    subscriptions.append((
        random.choice(CUSTOMER_IDS),
        49900,
        'failed_charge',
        None,  # NULL mandate_status - should block retry_charge action
        datetime.now() - timedelta(hours=12),
        2
    ))

    # Edge case: Active subscription but NULL last_charge_attempt
    subscriptions.append((
        random.choice(CUSTOMER_IDS),
        99900,
        'active',
        'active',
        None,  # NULL last_charge_attempt - unusual state
        0
    ))

    cursor.executemany(
        """
        INSERT INTO subscriptions
        (customer_id, plan_amount, status, mandate_status, last_charge_attempt, consecutive_failures)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        subscriptions
    )

    print(f"✓ Generated {len(subscriptions)} subscriptions (including {3} hard cases)")

def main():
    print("Starting seed data generation...")

    conn = get_connection()

    try:
        # Clear existing data
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE recovery_actions, transactions, checkout_sessions, subscriptions CASCADE")
        conn.commit()
        print("✓ Cleared existing data")

        # Note: mandate_status column must allow NULL for edge case testing
        # If schema enforces NOT NULL, this seed will fail - intentional to catch schema mismatch
        cursor.execute("""
            ALTER TABLE subscriptions
            ALTER COLUMN mandate_status DROP NOT NULL
        """)
        conn.commit()
        print("✓ Schema adjustment: mandate_status now allows NULL for edge case testing")

        # Generate seed data
        generate_transactions(conn, 200)
        generate_checkout_sessions(conn, 80)
        generate_subscriptions(conn, 50)

        conn.commit()

        # Summary
        cursor.execute("SELECT COUNT(*) as count FROM transactions")
        tx_count = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM checkout_sessions")
        cs_count = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM subscriptions")
        sub_count = cursor.fetchone()['count']

        total = tx_count + cs_count + sub_count

        print(f"\n✓ Seed data generation complete!")
        print(f"  Total records: {total}")
        print(f"  - Transactions: {tx_count}")
        print(f"  - Checkout Sessions: {cs_count}")
        print(f"  - Subscriptions: {sub_count}")
        print(f"\n  Edge cases included:")
        print(f"  - Transactions: NULL failure_reason, zero amount, negative amount, very large amount (1 crore)")
        print(f"  - Checkout: inconsistent state (completed+abandoned_at), abandoned stage")
        print(f"  - Subscriptions: NULL mandate_status, NULL last_charge_attempt")

    except Exception as e:
        conn.rollback()
        print(f"✗ Error generating seed data: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
