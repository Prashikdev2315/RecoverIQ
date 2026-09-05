from typing import Dict, Any
from agent.llm_client import call_claude, parse_json_response

# Pre-approved Hinglish templates for initial messages (TRAI/WhatsApp compliant)
# Templates are 60-70% static text with variable slots - matches Meta's requirement
HINGLISH_TEMPLATES = {
    'payment_failed': "Namaste {name}, aapka ₹{amount} ka payment pending hai. Issue: {issue}. Kripya payment complete karein: {url}",
    'checkout_abandoned': "Hi {name}! Aapka ₹{amount} ka cart save hai. Checkout karne ke liye yahan click karein: {url}",
    'subscription_failed': "Dear {name}, aapka subscription payment fail ho gaya (₹{amount}). Please payment method update karein: {url}",
    'insufficient_funds': "Namaste {name}, ₹{amount} ka payment insufficient balance ke karan pending hai. Kripya account check karein.",
    'card_expired': "Hi {name}, aapka payment card expire ho gaya hai. ₹{amount} ka payment ke liye naya card add karein: {url}",
    'retry_reminder': "Dear {name}, hum ₹{amount} ka payment retry karenge. Kripya account me sufficient balance ensure karein."
}

ENGLISH_TEMPLATES = {
    'payment_failed': "Hello {name}, your payment of ₹{amount} is pending. Issue: {issue}. Please complete payment: {url}",
    'checkout_abandoned': "Hi {name}! Your cart with ₹{amount} is saved. Complete checkout here: {url}",
    'subscription_failed': "Dear {name}, your subscription payment failed (₹{amount}). Please update payment method: {url}",
    'insufficient_funds': "Hello {name}, payment of ₹{amount} is pending due to insufficient balance. Please check your account.",
    'card_expired': "Hi {name}, your payment card has expired. Add new card for ₹{amount} payment: {url}",
    'retry_reminder': "Dear {name}, we will retry charging ₹{amount}. Please ensure sufficient balance in your account."
}

# Compliance filter rules
COMPLIANCE_RULES = """
REJECT if message contains:
- False urgency ("last chance", "account will be closed")
- Legal threats ("legal action", "court", "police")
- Misleading claims ("mandatory", "required by law")
- Excessive urgency markers (multiple "!!!", "URGENT")
- Shaming language
- Debt collection language
- Discount/promotional offers (must stay in "Service Implicit" category)

ACCEPT if message:
- Simply states the issue
- Offers a solution
- Includes a clear call-to-action
- Maintains respectful tone
"""

def generate_hinglish_message(
    customer_name: str,
    amount: int,
    issue_type: str,
    issue_details: str,
    urgency: str,
    channel: str = 'sms',
    is_follow_up: bool = False
) -> Dict[str, Any]:
    """
    Generate a Hinglish recovery message.

    TEMPLATE-FIRST APPROACH (TRAI/WhatsApp compliant):
    - Initial messages use pre-approved templates with variable slots
    - Follow-up messages (after customer reply) use LLM-generated free-form text

    Args:
        customer_name: Customer's name
        amount: Amount in paise
        issue_type: 'payment_failed', 'checkout_abandoned', 'subscription_failed'
        issue_details: Specific details about the issue
        urgency: 'low', 'medium', 'high', 'critical'
        channel: 'sms', 'whatsapp', 'email'
        is_follow_up: True if this is a response to customer reply (allows free-form)

    Returns:
        {
            'hinglish_message': str,
            'english_message': str,
            'passes_compliance': bool,
            'compliance_reason': str,
            'character_count': int,
            'generation_method': 'template' | 'llm'
        }
    """

    amount_rupees = amount / 100

    # INITIAL MESSAGE: Use template (WhatsApp/TRAI compliant)
    if not is_follow_up:
        return generate_from_template(
            customer_name=customer_name,
            amount_rupees=amount_rupees,
            issue_type=issue_type,
            issue_details=issue_details
        )

    # FOLLOW-UP MESSAGE: Use LLM (conversational, customer already engaged)
    return generate_with_llm(
        customer_name=customer_name,
        amount_rupees=amount_rupees,
        issue_type=issue_type,
        issue_details=issue_details,
        urgency=urgency,
        channel=channel
    )

def generate_from_template(
    customer_name: str,
    amount_rupees: float,
    issue_type: str,
    issue_details: str
) -> Dict[str, Any]:
    """
    Generate message from pre-approved template.
    This is WhatsApp Business API compliant (60-70% static text).
    """

    # Map issue types to template keys
    template_key = issue_type

    # Use more specific template if available
    if 'insufficient' in issue_details.lower():
        template_key = 'insufficient_funds'
    elif 'expired' in issue_details.lower():
        template_key = 'card_expired'
    elif 'subscription' in issue_type.lower():
        template_key = 'subscription_failed'
    elif 'abandoned' in issue_type.lower():
        template_key = 'checkout_abandoned'

    # Get template or fall back to generic
    hinglish_template = HINGLISH_TEMPLATES.get(template_key, HINGLISH_TEMPLATES['payment_failed'])
    english_template = ENGLISH_TEMPLATES.get(template_key, ENGLISH_TEMPLATES['payment_failed'])

    # Fill template variables — truncate at word boundary to avoid mid-word cuts like "likely ."
    def truncate_issue(text: str, max_len: int = 30) -> str:
        if not text:
            return "payment issue"
        if len(text) <= max_len:
            return text
        truncated = text[:max_len].rsplit(' ', 1)[0]
        return truncated.rstrip(' ,;')

    issue_short = truncate_issue(issue_details)

    hinglish_msg = hinglish_template.format(
        name=customer_name,
        amount=f"{amount_rupees:.2f}",
        issue=issue_short,
        url="[Payment Link]"  # In production, this would be actual payment URL
    )

    english_msg = english_template.format(
        name=customer_name,
        amount=f"{amount_rupees:.2f}",
        issue=issue_short,
        url="[Payment Link]"
    )

    # Templates are pre-approved, so compliance check is simple
    compliance_check = check_compliance(hinglish_msg, english_msg)

    return {
        'hinglish_message': hinglish_msg,
        'english_message': english_msg,
        'passes_compliance': compliance_check['passes'],
        'compliance_reason': compliance_check['reason'],
        'character_count': len(hinglish_msg),
        'generation_method': 'template'
    }

def generate_with_llm(
    customer_name: str,
    amount_rupees: float,
    issue_type: str,
    issue_details: str,
    urgency: str,
    channel: str
) -> Dict[str, Any]:
    """
    Generate free-form Hinglish message using Claude (for follow-ups only).
    """

    prompt = f"""Generate a conversational follow-up message for this scenario:

Customer: {customer_name}
Amount: ₹{amount_rupees:.2f}
Issue: {issue_type}
Details: {issue_details}
Urgency: {urgency}
Channel: {channel}

IMPORTANT: This is a FOLLOW-UP message (customer already replied).
- Conversational and natural
- Natural Hinglish (Hindi+English code-mix) in Latin script
- Under 160 characters for SMS
- Polite, no threats or urgency
- NO discounts or promotional offers

Provide your response in this exact JSON format:
{{
    "hinglish_message": "Natural Hinglish message here",
    "english_message": "English equivalent here"
}}

Generate the message now:"""

    result = call_claude(prompt, temperature=0.7)

    if not result['success']:
        # Fallback to safe generic message
        return {
            'hinglish_message': f"Dear {customer_name}, payment pending hai. Please complete karein.",
            'english_message': f"Dear {customer_name}, your payment is pending. Please complete it.",
            'passes_compliance': True,
            'compliance_reason': 'LLM unavailable, used safe fallback',
            'character_count': 0,
            'generation_method': 'llm_fallback',
            'llm_log': result['log']
        }

    parsed = parse_json_response(result['response'])

    if not parsed or 'hinglish_message' not in parsed:
        # Parse failed, use fallback
        return {
            'hinglish_message': f"Dear {customer_name}, payment pending hai. Please complete karein.",
            'english_message': f"Dear {customer_name}, your payment is pending. Please complete it.",
            'passes_compliance': True,
            'compliance_reason': 'LLM parse failed, used safe fallback',
            'character_count': 0,
            'generation_method': 'llm_fallback',
            'llm_log': result['log']
        }

    hinglish_msg = parsed['hinglish_message']
    english_msg = parsed.get('english_message', '')

    # Run compliance filter
    compliance_check = check_compliance(hinglish_msg, english_msg)

    if not compliance_check['passes']:
        print(f"⚠ LLM message failed compliance: {compliance_check['reason']}")
        print(f"  Original: {hinglish_msg}")

        # Use safe fallback instead of regenerating
        return {
            'hinglish_message': f"Dear {customer_name}, payment pending hai. Please help karein.",
            'english_message': f"Dear {customer_name}, your payment is pending. Please help.",
            'passes_compliance': True,
            'compliance_reason': 'LLM output failed compliance, used safe fallback',
            'character_count': 0,
            'generation_method': 'llm_fallback',
            'llm_log': result['log']
        }

    return {
        'hinglish_message': hinglish_msg,
        'english_message': english_msg,
        'passes_compliance': True,
        'compliance_reason': 'Passed all checks',
        'character_count': len(hinglish_msg),
        'generation_method': 'llm',
        'llm_log': result['log']
    }

def check_compliance(hinglish_msg: str, english_msg: str) -> Dict[str, bool]:
    """
    Check if message passes compliance rules.
    Returns dict with 'passes' bool and 'reason' string.
    """

    msg_lower = (hinglish_msg + ' ' + english_msg).lower()

    # Check for forbidden phrases
    forbidden_phrases = [
        'last chance', 'final warning', 'legal action', 'court', 'police',
        'account will be closed', 'account blocked', 'mandatory', 'required by law',
        'debt', 'defaulter', 'blacklist'
    ]

    for phrase in forbidden_phrases:
        if phrase in msg_lower:
            return {
                'passes': False,
                'reason': f'Contains forbidden phrase: "{phrase}"'
            }

    # Check for excessive urgency markers
    urgency_count = msg_lower.count('!!!') + msg_lower.count('urgent')
    if urgency_count > 1:
        return {
            'passes': False,
            'reason': 'Excessive urgency markers'
        }

    # Check for shaming language
    shame_words = ['shame', 'irresponsible', 'bad credit', 'dishonest']
    for word in shame_words:
        if word in msg_lower:
            return {
                'passes': False,
                'reason': f'Contains shaming language: "{word}"'
            }

    # Check for discount/promotional language (must stay in "Service Implicit" TRAI category)
    promo_words = ['discount', 'offer', 'cashback', 'free', 'bonus', 'reward', 'save', 'deal', 'promotion']
    for word in promo_words:
        if word in msg_lower:
            return {
                'passes': False,
                'reason': f'Contains promotional language: "{word}" - must stay in Service Implicit category'
            }

    # Check length for SMS
    if len(hinglish_msg) > 160:
        return {
            'passes': False,
            'reason': f'Message too long: {len(hinglish_msg)} chars (max 160)'
        }

    return {
        'passes': True,
        'reason': 'All checks passed'
    }

def generate_message_for_action(
    action: str,
    record: Dict[str, Any],
    diagnosis: Dict[str, Any],
    customer_name: str = None
) -> Dict[str, Any]:
    """
    Generate appropriate message based on action type and context.

    Args:
        action: Action type from decision engine
        record: The original record (transaction/checkout/subscription)
        diagnosis: Diagnosis from diagnoser
        customer_name: Customer name (defaults to generic if not provided)

    Returns:
        Message generation result dict
    """

    if not customer_name:
        customer_name = "Customer"

    amount = record.get('amount') or record.get('cart_value') or record.get('plan_amount', 0)
    root_cause = diagnosis.get('root_cause', 'Unknown issue')

    # Map action to issue type and details
    if action == 'send_reminder_sms':
        if 'cart_value' in record:
            issue_type = 'checkout_abandoned'
            issue_details = f"Cart abandoned at {record.get('stage_reached')}"
            urgency = 'medium'
        else:
            issue_type = 'payment_reminder'
            issue_details = root_cause
            urgency = 'medium'

    elif action == 'send_payment_link':
        issue_type = 'payment_failed'
        issue_details = root_cause
        urgency = 'high'

    elif action == 'retry_charge':
        issue_type = 'subscription_failed'
        issue_details = root_cause
        urgency = 'medium'

    elif action == 'offer_alternate_method':
        issue_type = 'payment_method_issue'
        issue_details = root_cause
        urgency = 'high'

    else:
        # No message needed for other actions
        return {
            'hinglish_message': None,
            'english_message': None,
            'passes_compliance': True,
            'compliance_reason': 'No message needed for this action',
            'character_count': 0
        }

    return generate_hinglish_message(
        customer_name=customer_name,
        amount=amount,
        issue_type=issue_type,
        issue_details=issue_details,
        urgency=urgency,
        channel='sms',
        is_follow_up=False  # Always use template for initial messages
    )
