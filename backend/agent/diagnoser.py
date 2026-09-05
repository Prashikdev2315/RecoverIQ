import json
from typing import Dict, Any, List
from datetime import datetime, timedelta
from agent.llm_client import call_claude, parse_json_response
from agent.error_taxonomy import normalize, CanonicalCategory, get_retry_recommendation, is_recoverable

def diagnose(record: Dict[str, Any], classification: Dict[str, Any], transaction_history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Determine root cause of the issue.
    Uses rules-first approach, falls back to LLM for ambiguous cases.

    Returns:
        {
            'diagnosis': str,
            'root_cause': str,
            'is_recoverable': bool,
            'recommended_action_hint': str,
            'method': 'rules' | 'llm',
            'llm_log': dict (if LLM was used)
        }
    """

    event_type = classification['event_type']

    if event_type.value == 'transaction':
        return diagnose_transaction(record, classification, transaction_history)
    elif event_type.value == 'checkout_session':
        return diagnose_checkout_session(record, classification)
    elif event_type.value == 'subscription':
        return diagnose_subscription(record, classification)
    else:
        return {
            'diagnosis': 'unknown_event_type',
            'root_cause': f'Cannot diagnose event type: {event_type}',
            'is_recoverable': False,
            'recommended_action_hint': 'no_action',
            'method': 'rules'
        }

def diagnose_transaction(record: Dict[str, Any], classification: Dict[str, Any], transaction_history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Diagnose failed transaction using error taxonomy normalization, then rules."""

    failure_reason = record.get('failure_reason')
    retry_count = record.get('retry_count', 0)
    payment_method = record.get('payment_method')
    status = record.get('status')

    # STEP 1: Normalize raw failure_reason to canonical category
    canonical = normalize(
        raw_code=None,  # We don't have raw error codes in seed data
        raw_reason=failure_reason,
        status=status
    )

    # STEP 2: Get retry recommendation from taxonomy
    retry_rec = get_retry_recommendation(canonical)

    # STEP 3: Route based on canonical category
    if canonical == CanonicalCategory.HARD_INSUFFICIENT_FUNDS:
        return {
            'diagnosis': 'insufficient_funds',
            'root_cause': 'Customer lacks sufficient balance in account',
            'is_recoverable': True,
            'recommended_action_hint': 'send_reminder_sms',
            'method': 'rules',
            'confidence_modifier': 0.0,
            'canonical_category': canonical.value
        }

    if canonical == CanonicalCategory.HARD_CARD_EXPIRED:
        return {
            'diagnosis': 'card_expired',
            'root_cause': 'Payment card has expired',
            'is_recoverable': True,
            'recommended_action_hint': 'offer_alternate_method',
            'method': 'rules',
            'confidence_modifier': 0.0,
            'canonical_category': canonical.value
        }

    if canonical == CanonicalCategory.HARD_INVALID_CVV:
        return {
            'diagnosis': 'invalid_cvv',
            'root_cause': 'Incorrect CVV entered',
            'is_recoverable': True,
            'recommended_action_hint': 'send_payment_link',
            'method': 'rules',
            'confidence_modifier': 0.0,
            'canonical_category': canonical.value
        }

    if canonical == CanonicalCategory.HARD_CARD_DECLINED:
        if retry_count >= 2:
            return {
                'diagnosis': 'persistent_bank_decline',
                'root_cause': 'Bank repeatedly declining transaction, possible fraud alert or account issue',
                'is_recoverable': True,
                'recommended_action_hint': 'escalate_to_human',
                'method': 'rules',
                'confidence_modifier': -0.2,
                'canonical_category': canonical.value
            }
        return {
            'diagnosis': 'bank_declined',
            'root_cause': 'Bank declined transaction, reason unclear',
            'is_recoverable': True,
            'recommended_action_hint': 'send_payment_link',
            'method': 'rules',
            'confidence_modifier': -0.1,
            'canonical_category': canonical.value
        }

    if canonical in [CanonicalCategory.SOFT_GATEWAY_TIMEOUT, CanonicalCategory.SOFT_NETWORK_ERROR]:
        return {
            'diagnosis': 'transient_failure',
            'root_cause': 'Temporary network or gateway issue',
            'is_recoverable': True,
            'recommended_action_hint': 'send_payment_link',
            'method': 'rules',
            'confidence_modifier': 0.1,
            'canonical_category': canonical.value
        }

    # Terminal failures
    if canonical in [
        CanonicalCategory.TERMINAL_MANDATE_CANCELLED,
        CanonicalCategory.TERMINAL_MANDATE_REVOKED,
        CanonicalCategory.TERMINAL_FRAUD_SUSPECTED
    ]:
        return {
            'diagnosis': canonical.value,
            'root_cause': f'Terminal failure: {canonical.value}',
            'is_recoverable': False,
            'recommended_action_hint': 'escalate_to_human',
            'method': 'rules',
            'confidence_modifier': -0.3,
            'canonical_category': canonical.value
        }

    # Unknown or ambiguous - use LLM fallback
    return diagnose_with_llm_transaction(record, classification, transaction_history)

def diagnose_with_llm_transaction(record: Dict[str, Any], classification: Dict[str, Any], transaction_history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Use LLM to diagnose ambiguous transaction failure."""

    # Pre-compute history string (Python 3.8 doesn't allow backslashes in f-string expressions)
    if transaction_history:
        history_str = "Transaction History (last 5):\n" + json.dumps(transaction_history[:5], indent=2, default=str)
    else:
        history_str = "No transaction history available."

    prompt = f"""Analyze this failed payment transaction and provide a diagnosis.

Transaction Details:
- Amount: \u20b9{record.get('amount', 0)/100:.2f}
- Payment Method: {record.get('payment_method')}
- Retry Count: {record.get('retry_count', 0)}
- Failure Reason: {record.get('failure_reason') or 'Not specified'}
- Created: {record.get('created_at')}

Classification:
- Severity: {classification.get('severity')}
- Fraud Indicators: {classification.get('fraud_indicators', [])}

{history_str}

Provide your diagnosis in this exact JSON format:
{{
    "diagnosis": "short_label",
    "root_cause": "detailed explanation",
    "is_recoverable": true/false,
    "recommended_action_hint": "send_reminder_sms|send_payment_link|offer_alternate_method|escalate_to_human|no_action",
    "confidence_modifier": -0.3 to 0.3 (adjustment based on uncertainty)
}}"""

    result = call_claude(prompt, temperature=0.3)

    if not result['success']:
        # Fallback to conservative rules-based decision
        return {
            'diagnosis': 'llm_unavailable_unknown_failure',
            'root_cause': f"LLM unavailable, original failure reason: {record.get('failure_reason')}",
            'is_recoverable': False,
            'recommended_action_hint': 'escalate_to_human',
            'method': 'rules_fallback',
            'llm_log': result['log'],
            'confidence_modifier': -0.3
        }

    parsed = parse_json_response(result['response'])

    if not parsed:
        return {
            'diagnosis': 'llm_parse_failed',
            'root_cause': 'LLM response could not be parsed',
            'is_recoverable': False,
            'recommended_action_hint': 'escalate_to_human',
            'method': 'llm_failed',
            'llm_log': result['log'],
            'confidence_modifier': -0.3
        }

    return {
        'diagnosis': parsed.get('diagnosis', 'unknown'),
        'root_cause': parsed.get('root_cause', 'Unknown'),
        'is_recoverable': parsed.get('is_recoverable', False),
        'recommended_action_hint': parsed.get('recommended_action_hint', 'escalate_to_human'),
        'method': 'llm',
        'llm_log': result['log'],
        'confidence_modifier': parsed.get('confidence_modifier', -0.2)
    }

def diagnose_checkout_session(record: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
    """Diagnose checkout abandonment."""

    stage_reached = record.get('stage_reached')
    device = record.get('device')
    cart_value = record.get('cart_value', 0)

    if stage_reached == 'otp':
        return {
            'diagnosis': 'abandoned_at_otp',
            'root_cause': 'Customer reached OTP stage but did not complete, high intent',
            'is_recoverable': True,
            'recommended_action_hint': 'send_reminder_sms',
            'method': 'rules',
            'confidence_modifier': 0.2
        }

    if stage_reached == 'payment_page':
        return {
            'diagnosis': 'abandoned_at_payment',
            'root_cause': 'Customer abandoned at payment page, moderate intent',
            'is_recoverable': True,
            'recommended_action_hint': 'send_reminder_sms',
            'method': 'rules',
            'confidence_modifier': 0.1
        }

    if stage_reached == 'cart':
        if cart_value >= 50000:
            return {
                'diagnosis': 'high_value_cart_abandonment',
                'root_cause': 'High-value cart abandoned early, possible price sensitivity',
                'is_recoverable': True,
                'recommended_action_hint': 'send_reminder_sms',
                'method': 'rules',
                'confidence_modifier': 0.0
            }
        return {
            'diagnosis': 'low_intent_abandonment',
            'root_cause': 'Cart abandoned early, low intent',
            'is_recoverable': True,
            'recommended_action_hint': 'send_reminder_sms',
            'method': 'rules',
            'confidence_modifier': -0.1
        }

    return {
        'diagnosis': 'general_abandonment',
        'root_cause': f'Checkout abandoned at {stage_reached}',
        'is_recoverable': True,
        'recommended_action_hint': 'send_reminder_sms',
        'method': 'rules',
        'confidence_modifier': 0.0
    }

def diagnose_subscription(record: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
    """Diagnose subscription failure."""

    consecutive_failures = record.get('consecutive_failures', 0)
    mandate_status = record.get('mandate_status')
    plan_amount = record.get('plan_amount', 0)

    if mandate_status == 'revoked':
        return {
            'diagnosis': 'mandate_revoked',
            'root_cause': 'Customer revoked payment mandate, cannot auto-retry',
            'is_recoverable': True,
            'recommended_action_hint': 'escalate_to_human',
            'method': 'rules',
            'confidence_modifier': -0.2
        }

    if mandate_status == 'pending':
        return {
            'diagnosis': 'mandate_pending',
            'root_cause': 'Payment mandate not yet confirmed',
            'is_recoverable': True,
            'recommended_action_hint': 'send_reminder_sms',
            'method': 'rules',
            'confidence_modifier': 0.0
        }

    if consecutive_failures >= 3:
        return {
            'diagnosis': 'repeated_subscription_failure',
            'root_cause': 'Multiple consecutive charge failures, possible persistent issue',
            'is_recoverable': True,
            'recommended_action_hint': 'offer_alternate_method',
            'method': 'rules',
            'confidence_modifier': -0.2
        }

    if consecutive_failures >= 1:
        return {
            'diagnosis': 'subscription_charge_failed',
            'root_cause': 'Recent charge failure, likely transient',
            'is_recoverable': True,
            'recommended_action_hint': 'retry_charge',
            'method': 'rules',
            'confidence_modifier': 0.1
        }

    return {
        'diagnosis': 'unknown_subscription_issue',
        'root_cause': 'Subscription failure with unclear cause',
        'is_recoverable': False,
        'recommended_action_hint': 'escalate_to_human',
        'method': 'rules',
        'confidence_modifier': -0.3
    }
