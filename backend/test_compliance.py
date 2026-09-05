import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.message_generator import generate_hinglish_message, check_compliance

def test_compliance_filter():
    """
    Test that the compliance filter blocks forbidden phrases and regenerates.
    """

    print("\n" + "="*80)
    print("COMPLIANCE FILTER TEST")
    print("="*80 + "\n")

    # Test cases with forbidden content
    test_cases = [
        {
            "name": "Forbidden: Legal threat",
            "message": "Pay now or legal action will be taken!",
            "should_fail": True
        },
        {
            "name": "Forbidden: Excessive urgency",
            "message": "URGENT!!! Last chance!!! Pay immediately!!!",
            "should_fail": True
        },
        {
            "name": "Forbidden: Shaming language",
            "message": "You are irresponsible for not paying",
            "should_fail": True
        },
        {
            "name": "Forbidden: False urgency",
            "message": "Last chance to pay or account will be closed",
            "should_fail": True
        },
        {
            "name": "Allowed: Polite reminder",
            "message": "Namaste, aapka payment pending hai. Please check karein.",
            "should_fail": False
        },
        {
            "name": "Allowed: Simple notification",
            "message": "Your payment of Rs 500 is pending. Complete it now.",
            "should_fail": False
        }
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        print(f"→ Test: {test['name']}")
        print(f"  Message: {test['message']}")

        result = check_compliance(test['message'], test['message'])

        if test['should_fail']:
            # Should be blocked
            if not result['passes']:
                print(f"  ✓ PASS: Correctly blocked - {result['reason']}")
                passed += 1
            else:
                print(f"  ✗ FAIL: Should have been blocked but passed")
                failed += 1
        else:
            # Should pass
            if result['passes']:
                print(f"  ✓ PASS: Correctly allowed")
                passed += 1
            else:
                print(f"  ✗ FAIL: Should have passed but was blocked - {result['reason']}")
                failed += 1

        print()

    # Test full generation with compliance
    print("→ Test: Full message generation with compliance")
    print("  Testing aggressive prompt that should trigger regeneration...")

    result = generate_hinglish_message(
        customer_name="Test Customer",
        amount=50000,
        issue_type="payment_failed",
        issue_details="Payment failed multiple times - URGENT ACTION REQUIRED",
        urgency="critical",
        channel="sms"
    )

    if result['passes_compliance']:
        print(f"  ✓ PASS: Generated compliant message")
        print(f"    Message: {result['hinglish_message']}")
        print(f"    Reason: {result['compliance_reason']}")
        passed += 1
    else:
        print(f"  ✗ FAIL: Could not generate compliant message")
        failed += 1

    print("\n" + "="*80)
    print(f"COMPLIANCE FILTER TEST: {passed} passed, {failed} failed")
    print("="*80 + "\n")

    return failed == 0

def main():
    try:
        success = test_compliance_filter()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
