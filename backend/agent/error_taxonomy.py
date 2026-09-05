"""
Error Taxonomy - Canonical Error Normalization Layer

Normalizes fragmented gateway/bank codes into a unified taxonomy for deterministic routing.
Production-grade systems normalize raw provider codes before diagnosis, not during.
"""

from enum import Enum
from typing import Optional

class CanonicalCategory(Enum):
    """
    Unified error categories for recovery routing.
    Maps all raw Razorpay/gateway/bank codes to one of these.
    """
    # Soft failures - likely transient, safe to retry
    SOFT_GATEWAY_TIMEOUT = "soft_gateway_timeout"
    SOFT_NETWORK_ERROR = "soft_network_error"
    SOFT_ISSUER_UNAVAILABLE = "soft_issuer_unavailable"

    # Hard failures - customer action required
    HARD_INSUFFICIENT_FUNDS = "hard_insufficient_funds"
    HARD_AUTH_FAILED = "hard_auth_failed"
    HARD_CARD_EXPIRED = "hard_card_expired"
    HARD_INVALID_CVV = "hard_invalid_cvv"
    HARD_CARD_DECLINED = "hard_card_declined"

    # Terminal failures - cannot retry
    TERMINAL_MANDATE_CANCELLED = "terminal_mandate_cancelled"
    TERMINAL_MANDATE_REVOKED = "terminal_mandate_revoked"
    TERMINAL_FRAUD_SUSPECTED = "terminal_fraud_suspected"

    # Abandonment
    SOFT_INTENT_DROP = "soft_intent_drop"

    # Unknown
    UNKNOWN_ERROR = "unknown_error"


def normalize(
    raw_code: Optional[str],
    raw_reason: Optional[str],
    status: Optional[str] = None
) -> CanonicalCategory:
    """
    Normalize raw provider error codes to canonical categories.

    Args:
        raw_code: Raw error code from Razorpay (e.g., 'BAD_REQUEST_ERROR', 'GATEWAY_ERROR')
        raw_reason: Failure reason string (e.g., 'insufficient_funds', 'card_expired')
        status: Payment/subscription status (e.g., 'failed', 'pending', 'abandoned')

    Returns:
        CanonicalCategory enum value
    """

    # Normalize to lowercase for comparison
    code = (raw_code or '').lower()
    reason = (raw_reason or '').lower()
    stat = (status or '').lower()

    # Map raw reasons to canonical categories
    # Based on Razorpay error codes and common gateway responses

    # Insufficient funds
    if 'insufficient' in reason or 'balance' in reason or 'fund' in reason:
        return CanonicalCategory.HARD_INSUFFICIENT_FUNDS

    # Card expired
    if 'expired' in reason or 'expir' in reason:
        return CanonicalCategory.HARD_CARD_EXPIRED

    # Invalid CVV / security code
    if 'cvv' in reason or 'security' in reason or 'cvc' in reason:
        return CanonicalCategory.HARD_INVALID_CVV

    # Authentication failed (OTP, 3DS, etc.)
    if 'auth' in reason or 'otp' in reason or '3ds' in reason or '3d secure' in reason:
        return CanonicalCategory.HARD_AUTH_FAILED

    # Bank/card declined (generic)
    if 'declined' in reason or 'reject' in reason:
        return CanonicalCategory.HARD_CARD_DECLINED

    # Timeout / network issues
    if 'timeout' in reason or 'gateway_timeout' in code:
        return CanonicalCategory.SOFT_GATEWAY_TIMEOUT

    if 'network' in reason or 'connection' in reason:
        return CanonicalCategory.SOFT_NETWORK_ERROR

    # Issuer/bank unavailable
    if 'issuer' in reason or 'unavailable' in reason or 'server_error' in code:
        return CanonicalCategory.SOFT_ISSUER_UNAVAILABLE

    # Mandate cancelled/revoked
    if 'mandate' in reason:
        if 'cancel' in reason or 'revok' in reason:
            return CanonicalCategory.TERMINAL_MANDATE_REVOKED
        return CanonicalCategory.TERMINAL_MANDATE_CANCELLED

    # Fraud suspected
    if 'fraud' in reason or 'suspect' in reason or 'risk' in reason:
        return CanonicalCategory.TERMINAL_FRAUD_SUSPECTED

    # Abandonment (checkout session specific)
    if stat in ['abandoned', 'cart', 'payment_page', 'otp'] and reason in ['', None, 'unknown']:
        return CanonicalCategory.SOFT_INTENT_DROP

    # Gateway errors (generic)
    if 'gateway_error' in code or 'gateway' in reason:
        return CanonicalCategory.SOFT_GATEWAY_TIMEOUT

    # Default to unknown if no mapping found
    return CanonicalCategory.UNKNOWN_ERROR


def get_retry_recommendation(category: CanonicalCategory) -> dict:
    """
    Get retry recommendation based on canonical category.

    Returns:
        {
            'should_retry': bool,
            'retry_type': 'automatic' | 'customer_initiated' | 'none',
            'suggested_delay_hours': int (for automatic retries)
        }
    """

    if category in [
        CanonicalCategory.SOFT_GATEWAY_TIMEOUT,
        CanonicalCategory.SOFT_NETWORK_ERROR,
        CanonicalCategory.SOFT_ISSUER_UNAVAILABLE
    ]:
        return {
            'should_retry': True,
            'retry_type': 'automatic',
            'suggested_delay_hours': 1  # Quick retry for transient issues
        }

    if category == CanonicalCategory.HARD_INSUFFICIENT_FUNDS:
        return {
            'should_retry': True,
            'retry_type': 'customer_initiated',
            'suggested_delay_hours': 48  # Wait for salary cycle (1st-5th of month ideal)
        }

    if category in [
        CanonicalCategory.HARD_CARD_EXPIRED,
        CanonicalCategory.HARD_INVALID_CVV,
        CanonicalCategory.HARD_AUTH_FAILED
    ]:
        return {
            'should_retry': True,
            'retry_type': 'customer_initiated',
            'suggested_delay_hours': 0  # Immediate customer action needed
        }

    if category in [
        CanonicalCategory.TERMINAL_MANDATE_CANCELLED,
        CanonicalCategory.TERMINAL_MANDATE_REVOKED,
        CanonicalCategory.TERMINAL_FRAUD_SUSPECTED
    ]:
        return {
            'should_retry': False,
            'retry_type': 'none',
            'suggested_delay_hours': 0
        }

    if category == CanonicalCategory.SOFT_INTENT_DROP:
        return {
            'should_retry': True,
            'retry_type': 'customer_initiated',
            'suggested_delay_hours': 1  # First reminder at 1 hour, then 24, then 72
        }

    # Unknown errors: conservative approach
    return {
        'should_retry': False,
        'retry_type': 'none',
        'suggested_delay_hours': 0
    }


def is_recoverable(category: CanonicalCategory) -> bool:
    """
    Quick check if a canonical category is recoverable.
    """
    terminal_categories = [
        CanonicalCategory.TERMINAL_MANDATE_CANCELLED,
        CanonicalCategory.TERMINAL_MANDATE_REVOKED,
        CanonicalCategory.TERMINAL_FRAUD_SUSPECTED
    ]
    return category not in terminal_categories
