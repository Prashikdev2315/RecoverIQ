import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from database import execute_query

# Guardrail thresholds (grounded in industry research)
MAX_SMS_PER_DAY_PER_CUSTOMER = 2  # Authentication/OTP failures: max 2 customer-facing nudges
MAX_PAYMENT_LINKS_PER_TRANSACTION = 3
MAX_RETRIES_PER_SUBSCRIPTION = 3  # Terminal stopping rule: 3-4 attempts (Razorpay native ceiling of 4)
MIN_CONFIDENCE_THRESHOLD = 0.6
FRAUD_DETECTION_WINDOW_HOURS = 24
FRAUD_DETECTION_FAILURE_THRESHOLD = 3

def execute_action(
    decision: Dict[str, Any],
    diagnosis: Dict[str, Any],
    classification: Dict[str, Any],
    record: Dict[str, Any],
    record_type: str,
    event_id: str = None
) -> Dict[str, Any]:
    """
    Enforce guardrails then execute the action.

    RBI COMPLIANCE GUARDRAIL (MANDATORY):
    Direct mandate token retries are unconditionally blocked.
    RBI e-mandate framework requires 24-hour pre-debit notice before any auto-debit.
    Subscription retries MUST route to send_payment_link (Customer-Initiated Transaction).

    Returns:
        {
            'status': 'executed' | 'blocked_by_guardrail' | 'proposed',
            'executed_action': str,
            'guardrail_reason': str (if blocked),
            'execution_log': dict
        }
    """

    action = decision['action']
    confidence = decision['confidence']
    customer_id = record.get('customer_id')
    record_id = record.get('id')

    # RBI COMPLIANCE GUARDRAIL: Block direct mandate retries (enforcement-level, not suggestion)
    # Defense-in-depth: Check BOTH record type AND actual mandate token presence
    if record_type == 'subscription' and action == 'retry_charge':
        mandate_status = record.get('mandate_status')

        # If this subscription has an active mandate, it MUST NOT be retried programmatically
        # RBI requires 24-hour pre-debit notice for any mandate-based auto-debit
        if mandate_status in ['active', 'paused', 'pending']:
            return {
                'status': 'blocked_by_guardrail',
                'executed_action': 'send_payment_link',
                'guardrail_reason': f'RBI e-mandate rule: mandate (status={mandate_status}) retries require fresh 24-hour pre-debit notice, not programmatic back-to-back retry. Routed to CIT payment link.',
                'execution_log': {
                    'original_action': action,
                    'override_reason': 'rbi_mandate_compliance',
                    'compliance_rule': 'RBI e-mandate framework - no direct token retry',
                    'mandate_status': mandate_status,
                    'enforced_action': 'send_payment_link',
                    'timestamp': datetime.now().isoformat()
                }
            }

        # If mandate_status is NULL or cancelled, this might be a one-time subscription payment
        # Still safer to route to CIT (payment link) for manual authorization
        elif mandate_status is None:
            return {
                'status': 'blocked_by_guardrail',
                'executed_action': 'send_payment_link',
                'guardrail_reason': 'RBI compliance (defensive): mandate_status unknown, routing to Customer-Initiated Transaction for safety.',
                'execution_log': {
                    'original_action': action,
                    'override_reason': 'rbi_mandate_compliance_defensive',
                    'compliance_rule': 'RBI e-mandate framework - unknown mandate status, fail safe',
                    'mandate_status': 'NULL',
                    'enforced_action': 'send_payment_link',
                    'timestamp': datetime.now().isoformat()
                }
            }

        # Only if mandate is explicitly 'cancelled' might retry be acceptable
        # but even then, route to payment link for re-authorization
        else:  # mandate_status == 'cancelled'
            return {
                'status': 'blocked_by_guardrail',
                'executed_action': 'send_payment_link',
                'guardrail_reason': f'RBI compliance: mandate cancelled, requires customer re-authorization. Routed to CIT payment link.',
                'execution_log': {
                    'original_action': action,
                    'override_reason': 'rbi_mandate_compliance',
                    'mandate_status': mandate_status,
                    'enforced_action': 'send_payment_link',
                    'timestamp': datetime.now().isoformat()
                }
            }

    # Collect ALL guardrail violations before deciding what to do
    violations = []

    # Check confidence threshold
    if confidence < MIN_CONFIDENCE_THRESHOLD:
        violations.append({
            'guardrail': 'confidence_threshold',
            'severity': 'high',
            'reason': f'Confidence {confidence:.2f} below threshold {MIN_CONFIDENCE_THRESHOLD}',
            'enforced_action': 'escalate_to_human'
        })

    # Check for fraud indicators
    fraud_check = check_fraud_indicators(customer_id, record_type)
    if fraud_check['is_suspicious']:
        violations.append({
            'guardrail': 'fraud_detection',
            'severity': 'critical',
            'reason': fraud_check['reason'],
            'indicators': fraud_check['indicators'],
            'enforced_action': 'escalate_to_human'
        })

    # Check for duplicate event
    duplicate_check = check_duplicate_event(record_id, record_type, event_id)
    if duplicate_check['is_duplicate']:
        violations.append({
            'guardrail': 'duplicate_event',
            'severity': 'high',
            'reason': 'Duplicate event already processed',
            'previous_action_id': duplicate_check['previous_action_id'],
            'dedup_method': duplicate_check.get('dedup_method', 'unknown'),
            'enforced_action': 'no_action'
        })

    # Action-specific guardrails
    if action == 'send_reminder_sms':
        rate_limit_check = check_sms_rate_limit(customer_id)
        if not rate_limit_check['allowed']:
            violations.append({
                'guardrail': 'sms_rate_limit',
                'severity': 'medium',
                'reason': rate_limit_check['reason'],
                'sms_count_today': rate_limit_check['count_today'],
                'enforced_action': 'no_action'
            })

    if action == 'send_payment_link':
        link_check = check_payment_link_limit(record_id)
        if not link_check['allowed']:
            violations.append({
                'guardrail': 'payment_link_limit',
                'severity': 'medium',
                'reason': link_check['reason'],
                'links_sent': link_check['count'],
                'enforced_action': 'escalate_to_human'
            })

    if action == 'retry_charge':
        retry_check = check_retry_limit(record_id, diagnosis)
        if not retry_check['allowed']:
            violations.append({
                'guardrail': 'retry_limit',
                'severity': 'medium',
                'reason': retry_check['reason'],
                'retry_count': retry_check['count'],
                'enforced_action': 'escalate_to_human'
            })

    if action == 'offer_alternate_method':
        same_method_check = check_same_method_failures(customer_id, record.get('payment_method'))
        if not same_method_check['should_offer']:
            violations.append({
                'guardrail': 'same_method_failures',
                'severity': 'low',
                'reason': same_method_check['reason'],
                'enforced_action': 'no_action'
            })

    # If any violations found, block action and log ALL of them
    if violations:
        # Pick highest severity violation for enforced action
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        violations.sort(key=lambda v: severity_order[v['severity']])
        primary_violation = violations[0]

        # Aggregate all reasons for logging
        all_reasons = ' | '.join([v['reason'] for v in violations])

        return {
            'status': 'blocked_by_guardrail',
            'executed_action': primary_violation['enforced_action'],
            'guardrail_reason': all_reasons,  # ALL violations logged
            'execution_log': {
                'original_action': action,
                'override_reason': 'multiple_guardrail_violations' if len(violations) > 1 else primary_violation['guardrail'],
                'violations': violations,  # Full list for audit
                'primary_violation': primary_violation['guardrail'],
                'timestamp': datetime.now().isoformat()
            }
        }

    # All guardrails passed - execute action
    execution_result = perform_action(action, decision, record, record_type)

    return {
        'status': 'executed',
        'executed_action': action,
        'guardrail_reason': None,
        'execution_log': execution_result
    }

def check_fraud_indicators(customer_id: str, record_type: str) -> Dict[str, Any]:
    """Check if customer shows signs of fraudulent activity."""

    if not customer_id:
        return {'is_suspicious': False, 'reason': None, 'indicators': []}

    # Check for multiple failures across different payment methods in short window
    query = """
        SELECT payment_method, COUNT(*) as failure_count
        FROM transactions
        WHERE customer_id = %s
          AND status = 'failed'
          AND created_at > NOW() - INTERVAL '%s hours'
        GROUP BY payment_method
    """

    try:
        results = execute_query(
            query,
            (customer_id, FRAUD_DETECTION_WINDOW_HOURS),
            fetch=True
        )

        if not results:
            return {'is_suspicious': False, 'reason': None, 'indicators': []}

        # Multiple different payment methods failing = suspicious
        method_count = len(results)
        total_failures = sum(r['failure_count'] for r in results)

        if method_count >= 3 and total_failures >= FRAUD_DETECTION_FAILURE_THRESHOLD:
            return {
                'is_suspicious': True,
                'reason': f'{total_failures} failures across {method_count} payment methods in {FRAUD_DETECTION_WINDOW_HOURS}h',
                'indicators': ['multiple_method_failures', 'high_failure_rate']
            }

        return {'is_suspicious': False, 'reason': None, 'indicators': []}

    except Exception as e:
        print(f"⚠ Fraud check failed: {e}")
        # Fail open - don't block on error
        return {'is_suspicious': False, 'reason': None, 'indicators': []}

def check_duplicate_event(record_id: str, record_type: str, event_id: str = None) -> Dict[str, Any]:
    """
    Check if we've already processed this event recently.

    Deduplication strategy:
    1. If event_id provided (from webhook): Check event_id (proper webhook dedup)
    2. If no event_id: Fall back to (target_type, target_id) check with 5-min window

    Args:
        record_id: Transaction/subscription/checkout UUID
        record_type: 'transaction', 'subscription', or 'checkout_session'
        event_id: Razorpay webhook event_id (evt_xxxxx format)
    """

    if not record_id:
        return {'is_duplicate': False, 'previous_action_id': None, 'dedup_method': 'none'}

    # STRATEGY 1: event_id-based dedup (proper webhook deduplication)
    if event_id:
        query = """
            SELECT id, created_at FROM recovery_actions
            WHERE event_id = %s
              AND created_at > NOW() - INTERVAL '24 hours'
            LIMIT 1
        """

        try:
            results = execute_query(query, (event_id,), fetch=True)

            if results and len(results) > 0:
                return {
                    'is_duplicate': True,
                    'previous_action_id': str(results[0]['id']),
                    'dedup_method': 'event_id',
                    'reason': f'Event {event_id} already processed'
                }

            return {
                'is_duplicate': False,
                'previous_action_id': None,
                'dedup_method': 'event_id'
            }

        except Exception as e:
            print(f"⚠ Event ID dedup check failed: {e}")
            # Fall through to target_id-based check

    # STRATEGY 2: target_id-based dedup (fallback for non-webhook actions)
    query = """
        SELECT id, created_at, executed_action
        FROM recovery_actions
        WHERE target_type = %s
          AND target_id = %s
          AND created_at > NOW() - INTERVAL '5 minutes'
        ORDER BY created_at DESC
        LIMIT 1
    """

    try:
        results = execute_query(query, (record_type, record_id), fetch=True)

        if results:
            # Only consider it a duplicate if processed very recently
            # This prevents webhook replay attacks while allowing legitimate retries
            return {
                'is_duplicate': True,
                'previous_action_id': str(results[0]['id']),
                'dedup_method': 'target_id'
            }

        return {'is_duplicate': False, 'previous_action_id': None, 'dedup_method': 'target_id'}

    except Exception as e:
        print(f"⚠ Duplicate check failed: {e}")
        # Fail open
        return {'is_duplicate': False, 'previous_action_id': None, 'dedup_method': 'error'}

def check_sms_rate_limit(customer_id: str) -> Dict[str, Any]:
    """Check if customer has exceeded SMS rate limit for today."""

    # SAFETY: Block if customer_id is missing - can't enforce rate limits without identity
    if not customer_id:
        return {
            'allowed': False,
            'reason': 'Cannot enforce SMS rate limit: customer_id missing from record',
            'count_today': 0
        }

    query = """
        SELECT COUNT(*) as sms_count
        FROM recovery_actions
        WHERE channel = 'sms'
          AND status = 'executed'
          AND created_at > NOW() - INTERVAL '1 day'
          AND target_id IN (
              SELECT id FROM transactions WHERE customer_id = %s
              UNION
              SELECT id FROM checkout_sessions WHERE customer_id = %s
              UNION
              SELECT id FROM subscriptions WHERE customer_id = %s
          )
    """

    try:
        results = execute_query(query, (customer_id, customer_id, customer_id), fetch=True)

        if not results:
            return {'allowed': True, 'reason': None, 'count_today': 0}

        count = results[0]['sms_count']

        if count >= MAX_SMS_PER_DAY_PER_CUSTOMER:
            return {
                'allowed': False,
                'reason': f'Customer already received {count} SMS today (limit: {MAX_SMS_PER_DAY_PER_CUSTOMER})',
                'count_today': count
            }

        return {'allowed': True, 'reason': None, 'count_today': count}

    except Exception as e:
        print(f"⚠ SMS rate limit check failed: {e}")
        # Fail safe - block on error (conservative)
        return {
            'allowed': False,
            'reason': f'Rate limit check failed: {str(e)}',
            'count_today': 0
        }

def check_payment_link_limit(transaction_id: str) -> Dict[str, Any]:
    """Check if transaction has exceeded payment link limit."""

    if not transaction_id:
        return {'allowed': True, 'reason': None, 'count': 0}

    query = """
        SELECT COUNT(*) as link_count
        FROM recovery_actions
        WHERE target_type = 'transaction'
          AND target_id = %s
          AND executed_action = 'send_payment_link'
          AND status IN ('executed', 'proposed')
    """

    try:
        results = execute_query(query, (transaction_id,), fetch=True)

        if not results:
            return {'allowed': True, 'reason': None, 'count': 0}

        count = results[0]['link_count']

        if count >= MAX_PAYMENT_LINKS_PER_TRANSACTION:
            return {
                'allowed': False,
                'reason': f'Transaction already has {count} payment links (limit: {MAX_PAYMENT_LINKS_PER_TRANSACTION})',
                'count': count
            }

        return {'allowed': True, 'reason': None, 'count': count}

    except Exception as e:
        print(f"⚠ Payment link limit check failed: {e}")
        return {'allowed': True, 'reason': None, 'count': 0}

def check_retry_limit(subscription_id: str, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    """Check if subscription has exceeded retry limit."""

    # Never retry card_expired or suspected fraud
    diagnosis_label = diagnosis.get('diagnosis', '')
    if 'expired' in diagnosis_label or 'fraud' in diagnosis_label:
        return {
            'allowed': False,
            'reason': f'Cannot retry: {diagnosis_label}',
            'count': 0
        }

    if not subscription_id:
        return {'allowed': True, 'reason': None, 'count': 0}

    query = """
        SELECT COUNT(*) as retry_count
        FROM recovery_actions
        WHERE target_type = 'subscription'
          AND target_id = %s
          AND executed_action = 'retry_charge'
          AND status IN ('executed', 'proposed')
    """

    try:
        results = execute_query(query, (subscription_id,), fetch=True)

        if not results:
            return {'allowed': True, 'reason': None, 'count': 0}

        count = results[0]['retry_count']

        if count >= MAX_RETRIES_PER_SUBSCRIPTION:
            return {
                'allowed': False,
                'reason': f'Subscription already retried {count} times (limit: {MAX_RETRIES_PER_SUBSCRIPTION})',
                'count': count
            }

        return {'allowed': True, 'reason': None, 'count': count}

    except Exception as e:
        print(f"⚠ Retry limit check failed: {e}")
        return {'allowed': True, 'reason': None, 'count': 0}

def check_same_method_failures(customer_id: str, payment_method: str) -> Dict[str, Any]:
    """Check if customer has 2+ failures on same payment method."""

    if not customer_id or not payment_method:
        return {'should_offer': False, 'reason': 'Missing customer or payment method', 'count': 0}

    query = """
        SELECT COUNT(*) as failure_count
        FROM transactions
        WHERE customer_id = %s
          AND payment_method = %s
          AND status = 'failed'
          AND created_at > NOW() - INTERVAL '7 days'
    """

    try:
        results = execute_query(query, (customer_id, payment_method), fetch=True)

        if not results:
            return {'should_offer': False, 'reason': 'No failure history', 'count': 0}

        count = results[0]['failure_count']

        if count >= 2:
            return {'should_offer': True, 'reason': None, 'count': count}

        return {
            'should_offer': False,
            'reason': f'Only {count} failure(s) on {payment_method} (need 2+)',
            'count': count
        }

    except Exception as e:
        print(f"⚠ Same method failure check failed: {e}")
        return {'should_offer': False, 'reason': 'Check failed', 'count': 0}

def perform_action(action: str, decision: Dict[str, Any], record: Dict[str, Any], record_type: str) -> Dict[str, Any]:
    """
    Simulate action execution.
    Real execution (Razorpay API calls, SMS sending) happens in Part 3.
    """

    execution_log = {
        'action': action,
        'timestamp': datetime.now().isoformat(),
        'simulated': True,
        'channel': decision.get('channel'),
        'language': decision.get('language')
    }

    if action == 'send_reminder_sms':
        execution_log['message'] = f"Reminder SMS would be sent to customer about {record_type}"
        execution_log['recipient'] = str(record.get('customer_id'))

    elif action == 'send_payment_link':
        execution_log['message'] = f"Payment link would be generated for transaction"
        execution_log['link'] = f"https://razorpay.com/payment/{record.get('id')}"

    elif action == 'retry_charge':
        execution_log['message'] = f"Subscription charge would be retried"
        execution_log['subscription_id'] = str(record.get('id'))

    elif action == 'offer_alternate_method':
        execution_log['message'] = f"Alternate payment method suggestion would be sent"
        execution_log['current_method'] = record.get('payment_method')

    elif action == 'escalate_to_human':
        execution_log['message'] = f"Case escalated to human review queue"
        execution_log['priority'] = 'high'

    else:
        execution_log['message'] = f"No action taken"

    print(f"  → Executed: {action}")

    return execution_log
