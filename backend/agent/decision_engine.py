from typing import Dict, Any
from enum import Enum

class Action(Enum):
    SEND_REMINDER_SMS = "send_reminder_sms"
    SEND_PAYMENT_LINK = "send_payment_link"
    RETRY_CHARGE = "retry_charge"
    OFFER_ALTERNATE_METHOD = "offer_alternate_method"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    NO_ACTION = "no_action"

# Industry benchmark figures from published aggregator/billing-platform data
# NOT measured from this project's own outcomes
# Sources: Razorpay, Stripe, and payment aggregator research
#
# Recovery by attempt number:
# - 1st retry: 40-50% success
# - 2nd retry: 20-25% success
# - 3rd retry: 8-12% success
# - 4th retry: <3% success
#
# Terminal stopping rule: 3-4 attempts (matching Razorpay native mandate ceiling of 4)
# Retry spacing for balance declines: 24-72 hours (higher recovery at month start: 1st-5th)
# Retry spacing for auth/OTP failures: Max 2 customer-facing nudges
# Checkout abandonment: 3-message sequence (1 hour, 24 hours, 72 hours)

# Base confidence scores for each action type
ACTION_BASE_CONFIDENCE = {
    Action.SEND_REMINDER_SMS: 0.75,
    Action.SEND_PAYMENT_LINK: 0.80,
    Action.RETRY_CHARGE: 0.70,
    Action.OFFER_ALTERNATE_METHOD: 0.75,
    Action.ESCALATE_TO_HUMAN: 0.95,
    Action.NO_ACTION: 0.90
}

def decide(diagnosis: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map diagnosis to action from fixed catalog.

    RBI Compliance Note:
    - For subscription/mandate failures, NEVER propose direct retry_charge
    - RBI e-mandate framework requires 24-hour pre-debit notice before auto-debit
    - Programmatic back-to-back mandate retries are non-compliant
    - Instead, route to send_payment_link (Customer-Initiated Transaction via OTP/UPI PIN)

    Returns:
        {
            'action': Action enum,
            'confidence': float (0-1),
            'reason': str,
            'channel': str,
            'language': str,
            'target_type': str (passed through for guardrail enforcement)
        }
    """

    hint = diagnosis.get('recommended_action_hint', 'no_action')
    is_recoverable = diagnosis.get('is_recoverable', False)
    severity = classification.get('severity')
    confidence_modifier = diagnosis.get('confidence_modifier', 0.0)
    target_type = classification.get('event_type')

    # If not recoverable, escalate or do nothing
    if not is_recoverable:
        action = Action.ESCALATE_TO_HUMAN
        reason = f"Not recoverable: {diagnosis.get('root_cause')}"
        base_confidence = ACTION_BASE_CONFIDENCE[action]

        return {
            'action': action.value,
            'confidence': min(1.0, base_confidence + confidence_modifier),
            'reason': reason,
            'channel': 'email',
            'language': 'en',
            'target_type': target_type.value if target_type else None
        }

    # Map hint to action
    action_map = {
        'send_reminder_sms': Action.SEND_REMINDER_SMS,
        'send_payment_link': Action.SEND_PAYMENT_LINK,
        'retry_charge': Action.RETRY_CHARGE,
        'offer_alternate_method': Action.OFFER_ALTERNATE_METHOD,
        'escalate_to_human': Action.ESCALATE_TO_HUMAN,
        'no_action': Action.NO_ACTION
    }

    action = action_map.get(hint, Action.ESCALATE_TO_HUMAN)

    # RBI COMPLIANCE: Never allow direct retry_charge for subscriptions/mandates
    # This is enforced here AND at guardrail level for defense-in-depth
    if target_type and target_type.value == 'subscription' and action == Action.RETRY_CHARGE:
        action = Action.SEND_PAYMENT_LINK
        reason = f"RBI compliance: Mandate retry requires fresh pre-debit notice. Routing to Customer-Initiated Transaction (payment link). Original issue: {diagnosis.get('root_cause')}"
    else:
        # Build reason normally
        reason = build_reason(diagnosis, classification, action)

    # Calculate confidence
    base_confidence = ACTION_BASE_CONFIDENCE[action]
    confidence = min(1.0, max(0.0, base_confidence + confidence_modifier))

    # Determine channel and language
    channel = determine_channel(action, classification)
    language = determine_language(classification)

    return {
        'action': action.value,
        'confidence': confidence,
        'reason': reason,
        'channel': channel,
        'language': language,
        'target_type': target_type.value if target_type else None
    }

def build_reason(diagnosis: Dict[str, Any], classification: Dict[str, Any], action: Action) -> str:
    """Build human-readable reason for the action."""

    root_cause = diagnosis.get('root_cause', 'Unknown issue')
    diagnosis_label = diagnosis.get('diagnosis', 'unknown')
    severity = classification.get('severity')

    if action == Action.SEND_REMINDER_SMS:
        return f"Send reminder via SMS: {root_cause}. Severity: {severity}."

    if action == Action.SEND_PAYMENT_LINK:
        return f"Send new payment link: {root_cause}. Customer can retry with corrected details."

    if action == Action.RETRY_CHARGE:
        return f"Auto-retry charge: {root_cause}. Issue appears transient."

    if action == Action.OFFER_ALTERNATE_METHOD:
        return f"Suggest alternate payment method: {root_cause}. Current method repeatedly failing."

    if action == Action.ESCALATE_TO_HUMAN:
        return f"Manual review required: {root_cause}. Automated recovery not recommended."

    if action == Action.NO_ACTION:
        return f"No action needed: {root_cause}."

    return f"Action {action.value}: {root_cause}"

def determine_channel(action: Action, classification: Dict[str, Any]) -> str:
    """Determine communication channel based on action and severity."""

    severity = classification.get('severity')

    if action == Action.SEND_REMINDER_SMS:
        return 'sms'

    if action == Action.SEND_PAYMENT_LINK:
        return 'payment_link'

    if action == Action.RETRY_CHARGE:
        return 'none'

    if action == Action.OFFER_ALTERNATE_METHOD:
        # High severity = SMS, otherwise email
        return 'sms' if severity and severity.value in ['high', 'critical'] else 'email'

    if action == Action.ESCALATE_TO_HUMAN:
        return 'email'

    return 'none'

def determine_language(classification: Dict[str, Any]) -> str:
    """
    Determine language for communication.

    Uses intelligent defaults to generate a natural mix of Hinglish and English:
    - 70% Hinglish (default for Indian market)
    - 30% English (for customers who may prefer it)

    In production, this would check customer preferences from their profile.
    """
    import random

    # Generate a natural mix: 70% Hinglish, 30% English
    # This ensures Hinglish messages appear by default without manual intervention
    return 'hinglish' if random.random() < 0.7 else 'en'
