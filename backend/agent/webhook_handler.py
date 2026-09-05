"""
Webhook handler for Razorpay payment events.
Handles payment.captured, subscription.charged events for false-positive tracking.
"""

import hmac
import hashlib
import json
from typing import Dict, Any
from datetime import datetime
from database import execute_query

def verify_razorpay_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify Razorpay webhook signature using HMAC-SHA256.

    Args:
        payload: Raw request body bytes
        signature: X-Razorpay-Signature header value
        secret: Webhook secret from Razorpay dashboard

    Returns:
        True if signature is valid
    """
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)

def handle_payment_success(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle payment.captured event.
    Updates recovery_actions status to 'recovered' if we sent a recovery action.
    """

    payment = event_data.get('payload', {}).get('payment', {}).get('entity', {})
    payment_id = payment.get('id')
    event_id = event_data.get('event_id')  # Extract from event root

    if not payment_id:
        return {'status': 'ignored', 'reason': 'No payment_id in payload'}

    # Find recovery_action for this payment and mark as recovered
    query = """
        UPDATE recovery_actions
        SET status = 'recovered',
            resolved_at = NOW(),
            event_id = %s
        WHERE target_type = 'transaction'
          AND target_id IN (
              SELECT id FROM transactions
              WHERE id::text = %s OR merchant_id::text = %s
          )
          AND status = 'executed'
          AND created_at > NOW() - INTERVAL '7 days'
        RETURNING id, target_id
    """

    try:
        results = execute_query(query, (event_id, payment_id, payment_id), fetch=True)

        if results and len(results) > 0:
            return {
                'status': 'success',
                'message': f'Marked {len(results)} recovery actions as recovered',
                'recovery_action_ids': [str(r['id']) for r in results]
            }

        return {
            'status': 'no_match',
            'message': 'No matching recovery action found (may not have been a recovery scenario)'
        }

    except Exception as e:
        print(f"✗ Error updating recovery status: {e}")
        return {'status': 'error', 'error': str(e)}

def handle_subscription_charged(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle subscription.charged event.
    Updates recovery_actions status to 'recovered' for subscription recovery.
    """

    subscription = event_data.get('payload', {}).get('subscription', {}).get('entity', {})
    subscription_id = subscription.get('id')
    event_id = event_data.get('event_id')  # Extract from event root

    if not subscription_id:
        return {'status': 'ignored', 'reason': 'No subscription_id in payload'}

    # Find recovery_action for this subscription
    query = """
        UPDATE recovery_actions
        SET status = 'recovered',
            resolved_at = NOW(),
            event_id = %s
        WHERE target_type = 'subscription'
          AND target_id IN (
              SELECT id FROM subscriptions
              WHERE id::text = %s
          )
          AND status = 'executed'
          AND created_at > NOW() - INTERVAL '7 days'
        RETURNING id, target_id
    """

    try:
        results = execute_query(query, (event_id, subscription_id), fetch=True)

        if results and len(results) > 0:
            return {
                'status': 'success',
                'message': f'Marked {len(results)} recovery actions as recovered',
                'recovery_action_ids': [str(r['id']) for r in results]
            }

        return {
            'status': 'no_match',
            'message': 'No matching recovery action found'
        }

    except Exception as e:
        print(f"✗ Error updating subscription recovery status: {e}")
        return {'status': 'error', 'error': str(e)}

def handle_payment_failed(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle payment.failed event.
    Creates new recovery action if eligible.
    """

    payment = event_data.get('payload', {}).get('payment', {}).get('entity', {})
    payment_id = payment.get('id')
    error_code = payment.get('error_code')
    error_description = payment.get('error_description')

    # This would trigger the normal pipeline
    # For now, just log it
    return {
        'status': 'acknowledged',
        'message': 'Payment failure logged, pipeline will process',
        'payment_id': payment_id
    }

def process_webhook_event(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route webhook event to appropriate handler.

    Supported events:
    - payment.captured: Mark recovery as successful
    - subscription.charged: Mark subscription recovery as successful
    - payment.failed: Trigger recovery pipeline (future)
    """

    event_type = event_data.get('event')
    event_id = event_data.get('event_id')

    print(f"Processing webhook: {event_type} (event_id: {event_id})")

    if event_type == 'payment.captured':
        return handle_payment_success(event_data)

    elif event_type == 'subscription.charged':
        return handle_subscription_charged(event_data)

    elif event_type == 'payment.failed':
        return handle_payment_failed(event_data)

    else:
        return {
            'status': 'ignored',
            'reason': f'Event type {event_type} not handled'
        }
