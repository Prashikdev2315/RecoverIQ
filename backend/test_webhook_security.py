import sys
import os
import hmac
import hashlib
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

def test_webhook_signature_verification():
    """
    Test that webhook signature verification works correctly.
    Tests both valid and invalid signatures.
    """

    print("\n" + "="*80)
    print("WEBHOOK SIGNATURE VERIFICATION TEST")
    print("="*80 + "\n")

    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_secret_key")

    # Test payload
    test_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test123",
                    "amount": 50000,
                    "method": "card",
                    "error_description": "insufficient_funds",
                    "created_at": 1234567890
                }
            }
        }
    }

    payload_bytes = json.dumps(test_payload).encode('utf-8')

    # Test 1: Valid signature
    print("→ Test 1: Valid signature")
    valid_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    from main import verify_webhook_signature

    result1 = verify_webhook_signature(payload_bytes, valid_signature, webhook_secret)

    if result1:
        print("  ✓ PASS: Valid signature accepted")
    else:
        print("  ✗ FAIL: Valid signature rejected")
        return False

    # Test 2: Invalid signature (tampered)
    print("\n→ Test 2: Invalid signature (tampered)")
    invalid_signature = "invalid_signature_12345"

    result2 = verify_webhook_signature(payload_bytes, invalid_signature, webhook_secret)

    if not result2:
        print("  ✓ PASS: Invalid signature rejected")
    else:
        print("  ✗ FAIL: Invalid signature accepted (security issue!)")
        return False

    # Test 3: Modified payload (signature mismatch)
    print("\n→ Test 3: Modified payload with original signature")
    modified_payload = test_payload.copy()
    modified_payload['payload']['payment']['entity']['amount'] = 100000  # Changed amount
    modified_bytes = json.dumps(modified_payload).encode('utf-8')

    result3 = verify_webhook_signature(modified_bytes, valid_signature, webhook_secret)

    if not result3:
        print("  ✓ PASS: Modified payload rejected (signature mismatch)")
    else:
        print("  ✗ FAIL: Modified payload accepted (security issue!)")
        return False

    print("\n" + "="*80)
    print("WEBHOOK SIGNATURE TEST: PASSED")
    print("="*80 + "\n")
    return True

def main():
    try:
        success = test_webhook_signature_verification()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
