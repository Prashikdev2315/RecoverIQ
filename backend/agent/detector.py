from enum import Enum
from typing import Dict, Any

class EventType(Enum):
    TRANSACTION = "transaction"
    CHECKOUT_SESSION = "checkout_session"
    SUBSCRIPTION = "subscription"

class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

def classify_event(record: Dict[str, Any], event_type: EventType) -> Dict[str, Any]:
    """
    Classify incoming event by type and severity.
    Returns dict with event_type, severity, and classification metadata.
    """

    if event_type == EventType.TRANSACTION:
        return classify_transaction(record)
    elif event_type == EventType.CHECKOUT_SESSION:
        return classify_checkout_session(record)
    elif event_type == EventType.SUBSCRIPTION:
        return classify_subscription(record)
    else:
        raise ValueError(f"Unknown event type: {event_type}")

def classify_transaction(record: Dict[str, Any]) -> Dict[str, Any]:
    """Classify transaction by severity based on amount and retry count."""

    amount = record.get('amount', 0)
    status = record.get('status')
    retry_count = record.get('retry_count', 0)
    failure_reason = record.get('failure_reason')

    # Only process failed transactions
    if status != 'failed':
        return {
            'event_type': EventType.TRANSACTION,
            'severity': None,
            'should_process': False,
            'reason': f'Transaction status is {status}, not failed'
        }

    # Determine severity
    if amount >= 100000:  # >= ₹1,000
        if retry_count >= 2:
            severity = Severity.CRITICAL
        else:
            severity = Severity.HIGH
    elif amount >= 50000:  # >= ₹500
        severity = Severity.HIGH if retry_count >= 2 else Severity.MEDIUM
    elif amount >= 10000:  # >= ₹100
        severity = Severity.MEDIUM if retry_count >= 1 else Severity.LOW
    else:
        severity = Severity.LOW

    # Check for fraud indicators
    fraud_indicators = []
    if retry_count >= 3:
        fraud_indicators.append('excessive_retries')

    return {
        'event_type': EventType.TRANSACTION,
        'severity': severity,
        'should_process': True,
        'amount': amount,
        'retry_count': retry_count,
        'failure_reason': failure_reason,
        'fraud_indicators': fraud_indicators,
        'reason': f'Failed transaction: ₹{amount/100:.2f}, {retry_count} retries'
    }

def classify_checkout_session(record: Dict[str, Any]) -> Dict[str, Any]:
    """Classify checkout abandonment by severity based on cart value and stage."""

    cart_value = record.get('cart_value', 0)
    stage_reached = record.get('stage_reached')

    # Only process abandoned or in-progress sessions
    if stage_reached == 'completed':
        return {
            'event_type': EventType.CHECKOUT_SESSION,
            'severity': None,
            'should_process': False,
            'reason': 'Checkout already completed'
        }

    # Determine severity based on cart value and stage
    # Later stages = higher intent = higher severity
    stage_multiplier = {
        'cart': 0.5,
        'payment_page': 1.0,
        'otp': 1.5,
        'abandoned': 1.0
    }.get(stage_reached, 0.5)

    effective_value = cart_value * stage_multiplier

    if effective_value >= 150000:  # High-intent, high-value
        severity = Severity.CRITICAL
    elif effective_value >= 75000:
        severity = Severity.HIGH
    elif effective_value >= 30000:
        severity = Severity.MEDIUM
    else:
        severity = Severity.LOW

    return {
        'event_type': EventType.CHECKOUT_SESSION,
        'severity': severity,
        'should_process': True,
        'cart_value': cart_value,
        'stage_reached': stage_reached,
        'effective_value': effective_value,
        'reason': f'Abandoned at {stage_reached}: ₹{cart_value/100:.2f}'
    }

def classify_subscription(record: Dict[str, Any]) -> Dict[str, Any]:
    """Classify subscription failure by severity based on consecutive failures and mandate status."""

    status = record.get('status')
    consecutive_failures = record.get('consecutive_failures', 0)
    mandate_status = record.get('mandate_status')
    plan_amount = record.get('plan_amount', 0)

    # Only process failed charges
    if status != 'failed_charge':
        return {
            'event_type': EventType.SUBSCRIPTION,
            'severity': None,
            'should_process': False,
            'reason': f'Subscription status is {status}, not failed_charge'
        }

    # Revoked mandate = cannot auto-retry
    if mandate_status == 'revoked':
        severity = Severity.CRITICAL
        requires_manual = True
    elif consecutive_failures >= 3:
        severity = Severity.CRITICAL
    elif consecutive_failures >= 2:
        severity = Severity.HIGH
    elif consecutive_failures >= 1:
        severity = Severity.MEDIUM
    else:
        severity = Severity.LOW

    requires_manual = mandate_status == 'revoked'

    return {
        'event_type': EventType.SUBSCRIPTION,
        'severity': severity,
        'should_process': True,
        'consecutive_failures': consecutive_failures,
        'mandate_status': mandate_status,
        'plan_amount': plan_amount,
        'requires_manual_intervention': requires_manual,
        'reason': f'Subscription failed: {consecutive_failures} consecutive failures, mandate {mandate_status}'
    }

def detect(record: Dict[str, Any], record_type: str) -> Dict[str, Any]:
    """
    Main detector entry point.

    Args:
        record: The event record (transaction/checkout_session/subscription)
        record_type: One of 'transaction', 'checkout_session', 'subscription'

    Returns:
        Classification result with event_type, severity, and metadata
    """

    event_type_map = {
        'transaction': EventType.TRANSACTION,
        'checkout_session': EventType.CHECKOUT_SESSION,
        'subscription': EventType.SUBSCRIPTION
    }

    event_type = event_type_map.get(record_type)
    if not event_type:
        raise ValueError(f"Invalid record_type: {record_type}")

    return classify_event(record, event_type)
