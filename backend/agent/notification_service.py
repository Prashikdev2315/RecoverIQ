import json
from typing import Dict, Any
from datetime import datetime
from database import execute_query
from agent.message_generator import generate_message_for_action

def simulate_send(
    action: str,
    channel: str,
    language: str,
    record: Dict[str, Any],
    diagnosis: Dict[str, Any],
    decision: Dict[str, Any],
    recovery_action_id: str
) -> Dict[str, Any]:
    """
    Simulate sending a notification.

    This is a simulated send for the hackathon - writes to database
    and returns success. Real SMS/WhatsApp integration would happen here.

    Args:
        action: The action being executed
        channel: Communication channel (sms, email, whatsapp_sim)
        language: Message language (en, hinglish)
        record: The source record
        diagnosis: Diagnosis from diagnoser
        decision: Decision from decision engine
        recovery_action_id: ID of the recovery_actions record

    Returns:
        {
            'success': bool,
            'message_sent': str (if applicable),
            'english_message': str (if Hinglish),
            'channel': str,
            'simulated': bool,
            'timestamp': str
        }
    """

    result = {
        'success': False,
        'message_sent': None,
        'english_message': None,
        'channel': channel,
        'simulated': True,
        'timestamp': datetime.now().isoformat()
    }

    # Actions that don't require messages
    if action in ['escalate_to_human', 'no_action']:
        result['success'] = True
        result['message_sent'] = f"Action: {action} (no customer notification)"
        return result

    # Generate message for actions that need customer communication
    if action in ['send_reminder_sms', 'send_payment_link', 'retry_charge', 'offer_alternate_method']:

        # Generate Hinglish message if language is hinglish
        if language == 'hinglish':
            message_result = generate_message_for_action(
                action=action,
                record=record,
                diagnosis=diagnosis,
                customer_name="Valued Customer"  # In real system, fetch from customer table
            )

            if message_result['passes_compliance']:
                result['success'] = True
                result['message_sent'] = message_result['hinglish_message']
                result['english_message'] = message_result['english_message']
                result['character_count'] = message_result['character_count']
                result['compliance_status'] = 'passed'

                # Store message in recovery_actions
                store_message(recovery_action_id, message_result)

                print(f"  ✓ Simulated send via {channel}:")
                print(f"    Hinglish: {result['message_sent']}")
                print(f"    English: {result['english_message']}")

            else:
                result['success'] = False
                result['error'] = f"Compliance check failed: {message_result['compliance_reason']}"
                print(f"  ✗ Message failed compliance: {message_result['compliance_reason']}")
        else:
            # Generate English message
            result['success'] = True
            result['message_sent'] = generate_english_message(action, record, diagnosis)
            result['language'] = 'en'

            print(f"  ✓ Simulated send via {channel}:")
            print(f"    Message: {result['message_sent']}")

    return result

def generate_english_message(action: str, record: Dict[str, Any], diagnosis: Dict[str, Any]) -> str:
    """Generate a simple English message for fallback."""

    amount = record.get('amount') or record.get('cart_value') or record.get('plan_amount', 0)
    amount_rupees = amount / 100

    if action == 'send_reminder_sms':
        if 'cart_value' in record:
            return f"Your cart with ₹{amount_rupees:.2f} is waiting. Complete your purchase now!"
        return f"Reminder: Your payment of ₹{amount_rupees:.2f} is pending. Please complete it."

    elif action == 'send_payment_link':
        return f"Your payment of ₹{amount_rupees:.2f} failed. Click here to retry: [Payment Link]"

    elif action == 'retry_charge':
        return f"We'll retry charging ₹{amount_rupees:.2f} for your subscription. Please ensure sufficient balance."

    elif action == 'offer_alternate_method':
        return f"Your payment of ₹{amount_rupees:.2f} failed multiple times. Try a different payment method?"

    return f"Action required for your transaction of ₹{amount_rupees:.2f}."

def store_message(recovery_action_id: str, message_result: Dict[str, Any]) -> None:
    """Store the generated message in the recovery_actions record."""

    try:
        query = """
            UPDATE recovery_actions
            SET reasoning_log = reasoning_log || %s::jsonb
            WHERE id = %s
        """

        message_log = {
            'message_generation': {
                'hinglish_message': message_result['hinglish_message'],
                'english_message': message_result['english_message'],
                'character_count': message_result['character_count'],
                'compliance_status': message_result.get('compliance_reason'),
                'timestamp': datetime.now().isoformat()
            }
        }

        execute_query(query, (json.dumps(message_log), recovery_action_id))

    except Exception as e:
        print(f"⚠ Failed to store message: {e}")
        # Non-critical, don't fail the send

def send_notification(
    action: str,
    channel: str,
    language: str,
    record: Dict[str, Any],
    diagnosis: Dict[str, Any],
    decision: Dict[str, Any],
    recovery_action_id: str
) -> Dict[str, Any]:
    """
    Main entry point for notification service.

    Note: Guardrails are already enforced by action_executor before this is called.
    This function only handles the actual sending (simulated).
    """

    return simulate_send(
        action=action,
        channel=channel,
        language=language,
        record=record,
        diagnosis=diagnosis,
        decision=decision,
        recovery_action_id=recovery_action_id
    )
