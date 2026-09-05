"""
Utility functions for DPDP compliance and data protection.
"""

import re
from typing import Optional


def mask_phone(phone: Optional[str]) -> str:
    """
    Mask phone number for DPDP compliance.

    Format: +91-XXXXX-90000 (country code + last few digits visible, middle masked)

    Args:
        phone: Phone number in any format

    Returns:
        Masked phone number string

    Examples:
        +919876543210 -> +91-XXXXX-3210
        9876543210 -> +91-XXXXX-3210
        +91-9876543210 -> +91-XXXXX-3210
    """

    if not phone:
        return "XXXXX-XXXX"

    # Remove all non-digit characters except leading +
    cleaned = re.sub(r'[^\d+]', '', str(phone))

    # Extract digits only
    digits = re.sub(r'[^\d]', '', cleaned)

    # Handle different formats
    if len(digits) >= 10:
        # Show last 4 digits
        last_digits = digits[-4:]
        country_code = "+91"  # Assume Indian numbers

        if cleaned.startswith('+91'):
            country_code = "+91"
        elif cleaned.startswith('+'):
            # Extract country code
            country_code = '+' + digits[:2]

        return f"{country_code}-XXXXX-{last_digits}"

    # If too short, mask completely
    return "XXXXX-XXXX"


def mask_customer_id(customer_id: Optional[str]) -> str:
    """
    Mask customer ID for logging.

    Shows first and last 4 characters, masks middle.

    Args:
        customer_id: Customer identifier (UUID or other)

    Returns:
        Masked customer ID

    Examples:
        550e8400-e29b-41d4-a716-446655440000 -> 550e-XXXX-0000
    """

    if not customer_id:
        return "XXXX-XXXX-XXXX"

    cid = str(customer_id)

    if len(cid) > 12:
        return f"{cid[:4]}-XXXX-{cid[-4:]}"
    elif len(cid) > 8:
        return f"{cid[:2]}-XXXX-{cid[-2:]}"
    else:
        return "XXXX-XXXX"


def mask_email(email: Optional[str]) -> str:
    """
    Mask email address for logging.

    Shows first 2 chars and domain, masks username middle.

    Args:
        email: Email address

    Returns:
        Masked email

    Examples:
        john.doe@example.com -> jo***@example.com
    """

    if not email or '@' not in email:
        return "***@***.***"

    parts = email.split('@')
    username = parts[0]
    domain = parts[1]

    if len(username) <= 2:
        masked_username = username[0] + '***'
    else:
        masked_username = username[:2] + '***'

    return f"{masked_username}@{domain}"


def mask_card_number(card: Optional[str]) -> str:
    """
    Mask card number (PCI-DSS compliance).

    Shows only last 4 digits.

    Args:
        card: Card number

    Returns:
        Masked card number

    Examples:
        4111111111111111 -> XXXX-XXXX-XXXX-1111
    """

    if not card:
        return "XXXX-XXXX-XXXX-XXXX"

    # Remove non-digits
    digits = re.sub(r'[^\d]', '', str(card))

    if len(digits) >= 4:
        last4 = digits[-4:]
        return f"XXXX-XXXX-XXXX-{last4}"

    return "XXXX-XXXX-XXXX-XXXX"


def sanitize_for_logging(data: dict) -> dict:
    """
    Sanitize a dictionary for safe logging.

    Masks PII fields automatically.

    Args:
        data: Dictionary potentially containing PII

    Returns:
        Dictionary with PII fields masked

    Masked fields:
        - phone, mobile, phone_number
        - email, email_address
        - customer_id, user_id
        - card_number, card
    """

    if not isinstance(data, dict):
        return data

    sanitized = data.copy()

    # Phone number fields
    phone_fields = ['phone', 'mobile', 'phone_number', 'contact']
    for field in phone_fields:
        if field in sanitized:
            sanitized[field] = mask_phone(sanitized[field])

    # Email fields
    email_fields = ['email', 'email_address']
    for field in email_fields:
        if field in sanitized:
            sanitized[field] = mask_email(sanitized[field])

    # Customer ID fields
    id_fields = ['customer_id', 'user_id', 'id']
    for field in id_fields:
        if field in sanitized and isinstance(sanitized[field], str):
            sanitized[field] = mask_customer_id(sanitized[field])

    # Card number fields
    card_fields = ['card_number', 'card', 'pan']
    for field in card_fields:
        if field in sanitized:
            sanitized[field] = mask_card_number(sanitized[field])

    return sanitized
