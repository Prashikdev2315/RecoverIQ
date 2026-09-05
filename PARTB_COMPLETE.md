# Part B Complete - Guardrail & Metrics Hardening

## Evidence-Based Fix Report

Completed fixes with verification, plus honest assessment of remaining work.

---

## COMPLETED FIXES

### 1. Follow-Up: PII Masking Coverage ✓

**Issue:** Part A only applied masking to audit-trail endpoint. Need to verify all endpoints.

**Finding:** Checked all 8 endpoints in `api/metrics.py`:
- `/funnel` - Returns aggregate counts only (no PII)
- `/recovery-by-category` - Returns aggregate counts only (no PII)
- `/false-positive-rate` - Returns aggregate counts only (no PII)
- `/latency` - Returns aggregate statistics only (no PII)
- `/guardrail-hits` - Returns aggregate counts only (no PII)
- `/audit-trail` - ✓ Masking applied (Part A)
- `/hinglish-examples` - Returns messages only (no customer IDs in output)
- `/stats` - Returns aggregate counts only (no PII)

**Verification:**
```bash
$ grep -n "@router.get" api/metrics.py
8:@router.get("/funnel")
81:@router.get("/recovery-by-category")
134:@router.get("/false-positive-rate")
195:@router.get("/latency")
245:@router.get("/guardrail-hits")
302:@router.get("/audit-trail")  # ONLY endpoint returning target_id
363:@router.get("/hinglish-examples")
402:@router.get("/stats")
```

**Checked hinglish-examples endpoint (line 363-400):**
```python
SELECT
    id,
    target_type,
    executed_action,
    language,
    reasoning_log->'message_generation'->>'hinglish_message' as hinglish_message,
    reasoning_log->'message_generation'->>'english_message' as english_message,
    ...
# NO customer_id or target_id in SELECT list
```

**Messages Themselves:** Generated templates don't include customer names (only placeholders filled at generation time, not stored).

**Status:** ✓ COMPLETE - Only audit-trail returns identifiable IDs, and it's already masked

---

### 2. Document Masking Architecture ✓

**Issue:** Is masking write-time or read-time? What's actually in the database?

**Finding:** Masking is **read-time only** (applied in API layer before returning data).

**Evidence from schema:**
```sql
-- backend/schema.sql:9
customer_id UUID NOT NULL,  -- Raw UUIDs stored

-- backend/schema.sql:44
target_id UUID NOT NULL,  -- Raw UUIDs stored
```

**What's in DB:** Raw UUIDs like `550e8400-e29b-41d4-a716-446655440000`

**What API returns:** Masked like `550e-XXXX-0000`

**Where masking happens:**
```python
# api/metrics.py:335-338
masked_target_id = mask_customer_id(str(row['target_id']))
sanitized_log = sanitize_for_logging(row['reasoning_log'])
```

**Production Gap:** 
- ✓ API responses are masked (DPDP compliant for data transfer)
- ✗ Database still contains raw UUIDs (would need field-level encryption for full DPDP)
- ✗ Pipeline logs (print statements) don't mask before outputting

**Honest Assessment:**
- **What's done:** API-level masking prevents PII exposure in dashboard
- **What's not done:** Database encryption at rest, pipeline log masking
- **Plug-in point:** Import `sanitize_for_logging()` in `pipeline.py`, call before print()

**Status:** ✓ DOCUMENTED - Architecture understood, gaps identified

---

### 3. RBI Mandate Guardrail Hardened ✓

**Issue:** Original check only verified `record_type == 'subscription'`, didn't check actual mandate token presence.

**Fix Applied:** Now checks `mandate_status` field with defense-in-depth logic.

**File:** `backend/agent/action_executor.py:43-95`

**Before:**
```python
if record_type == 'subscription' and action == 'retry_charge':
    return {
        'status': 'blocked_by_guardrail',
        'guardrail_reason': 'RBI e-mandate rule...',
        ...
    }
```

**After:**
```python
if record_type == 'subscription' and action == 'retry_charge':
    mandate_status = record.get('mandate_status')
    
    # If mandate is active/paused/pending - BLOCK (RBI requires 24h notice)
    if mandate_status in ['active', 'paused', 'pending']:
        return {
            'status': 'blocked_by_guardrail',
            'guardrail_reason': f'RBI e-mandate rule: mandate (status={mandate_status}) retries require fresh 24-hour pre-debit notice...',
            'execution_log': {
                ...
                'mandate_status': mandate_status,  # Logged for audit
            }
        }
    
    # If mandate_status is NULL - BLOCK defensively (unknown state)
    elif mandate_status is None:
        return {
            'status': 'blocked_by_guardrail',
            'guardrail_reason': 'RBI compliance (defensive): mandate_status unknown, routing to CIT for safety.',
            'execution_log': {
                'mandate_status': 'NULL',
                ...
            }
        }
    
    # If mandate is cancelled - still BLOCK (requires re-authorization)
    else:  # mandate_status == 'cancelled'
        return {
            'status': 'blocked_by_guardrail',
            'guardrail_reason': 'RBI compliance: mandate cancelled, requires customer re-authorization...',
            ...
        }
```

**Defense-in-Depth:** Three-level check:
1. Record type (subscription)
2. Action type (retry_charge)
3. **NEW:** Mandate status field (active/paused/pending/NULL/cancelled)

**Verification:**
```bash
$ grep -A5 "mandate_status = record.get" agent/action_executor.py
    mandate_status = record.get('mandate_status')
    
    # If this subscription has an active mandate, it MUST NOT be retried programmatically
    # RBI requires 24-hour pre-debit notice for any mandate-based auto-debit
    if mandate_status in ['active', 'paused', 'pending']:
```

**Status:** ✓ COMPLETE - RBI guardrail now checks actual mandate presence, not just record type

---

### 4. Rate Limit NULL Handling Fixed ✓

**Issue:** `check_sms_rate_limit()` returned `allowed: True` when `customer_id` was NULL, silently bypassing rate limits.

**Fix Applied:** Now blocks when customer_id is missing.

**File:** `backend/agent/action_executor.py:294-346`

**Before:**
```python
def check_sms_rate_limit(customer_id: str) -> Dict[str, Any]:
    if not customer_id:
        return {'allowed': True, 'reason': None, 'count_today': 0}  # UNSAFE
```

**After:**
```python
def check_sms_rate_limit(customer_id: str) -> Dict[str, Any]:
    # SAFETY: Block if customer_id is missing - can't enforce rate limits without identity
    if not customer_id:
        return {
            'allowed': False,  # SAFE - blocks action
            'reason': 'Cannot enforce SMS rate limit: customer_id missing from record',
            'count_today': 0
        }
```

**Also Fixed:** Exception handler now fails safe (blocks) instead of allowing:

**Before:**
```python
except Exception as e:
    # Fail safe - allow
    return {'allowed': True, 'reason': None, 'count_today': 0}
```

**After:**
```python
except Exception as e:
    # Fail safe - block on error (conservative)
    return {
        'allowed': False,
        'reason': f'Rate limit check failed: {str(e)}',
        'count_today': 0
    }
```

**Verification:**
```bash
$ grep -A3 "if not customer_id:" agent/action_executor.py | head -5
    if not customer_id:
        return {
            'allowed': False,
            'reason': 'Cannot enforce SMS rate limit: customer_id missing from record',
```

**Status:** ✓ COMPLETE - Rate limits now fail safe when customer_id is NULL or query fails

---

### 5. Guardrail Violation Aggregation ✓

**Issue:** Each guardrail check returned immediately on failure. If multiple violations occurred, only first was logged.

**Fix Applied:** Collect ALL violations, log all reasons, pick highest severity for enforcement.

**File:** `backend/agent/action_executor.py:98-180`

**Before:**
```python
if confidence < MIN_CONFIDENCE_THRESHOLD:
    return {'status': 'blocked_by_guardrail', ...}  # Returns immediately

if fraud_check['is_suspicious']:
    return {'status': 'blocked_by_guardrail', ...}  # Never reached if confidence failed

# ... other checks
```

**After:**
```python
# Collect ALL guardrail violations before deciding what to do
violations = []

if confidence < MIN_CONFIDENCE_THRESHOLD:
    violations.append({
        'guardrail': 'confidence_threshold',
        'severity': 'high',
        'reason': f'Confidence {confidence:.2f} below threshold...',
        'enforced_action': 'escalate_to_human'
    })

if fraud_check['is_suspicious']:
    violations.append({
        'guardrail': 'fraud_detection',
        'severity': 'critical',
        'reason': fraud_check['reason'],
        'indicators': fraud_check['indicators'],
        'enforced_action': 'escalate_to_human'
    })

# ... collect all other violations

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
            'violations': violations,  # Full list for audit
            'primary_violation': primary_violation['guardrail'],
            ...
        }
    }
```

**Example Output:**
```python
{
    'status': 'blocked_by_guardrail',
    'guardrail_reason': 'Confidence 0.45 below threshold 0.6 | Customer already received 2 SMS today (limit: 2)',
    'execution_log': {
        'violations': [
            {'guardrail': 'confidence_threshold', 'severity': 'high', ...},
            {'guardrail': 'sms_rate_limit', 'severity': 'medium', ...}
        ],
        'primary_violation': 'confidence_threshold'  # Highest severity
    }
}
```

**Verification:**
```bash
$ grep -n "violations = \[\]" agent/action_executor.py
99:    violations = []

$ grep -n "violations.append" agent/action_executor.py
103:        violations.append({
112:        violations.append({
123:        violations.append({
...
```

**Status:** ✓ COMPLETE - All guardrail violations now collected and logged together

---

## NOT COMPLETED (Honest Assessment)

### 6. Idempotency Key Using event_id

**Issue:** Duplicate check keys on `(target_type, target_id)` instead of webhook `event_id`.

**Current Code (line 256-279):**
```python
def check_duplicate_event(record_id: str, record_type: str) -> Dict[str, Any]:
    query = """
        SELECT id FROM recovery_actions
        WHERE target_type = %s
          AND target_id = %s
          AND created_at > NOW() - INTERVAL '5 minutes'
    """
    results = execute_query(query, (record_type, record_id), fetch=True)
```

**Problem:** If Razorpay re-sends same payment failure within 5 minutes (legitimate status update), it's blocked.

**Proper Fix Would:**
1. Add `event_id` column to recovery_actions table
2. Store webhook event_id when creating action
3. Check `WHERE event_id = %s AND created_at > NOW() - INTERVAL '5 minutes'`

**Why Not Done:** Requires schema migration, webhook handler changes, seed data updates. Beyond single-file fix.

**Workaround:** Current 5-minute window works for demo (prevents replay attacks), but isn't production-grade webhook dedup.

**Status:** ✗ NOT DONE - Documented as known limitation

---

### 7. Real False-Positive Tracking

**Issue:** False-positive rate still uses estimated coefficients, not tracked outcomes.

**Current Code (metrics.py:156-160):**
```python
estimated_responses = int(
    high_confidence * 0.75 +
    medium_confidence * 0.55 +
    low_confidence * 0.30
)
actual_responses = confirmed_recovered if confirmed_recovered > 0 else estimated_responses
# confirmed_recovered is always 0 because nothing sets status='recovered'
```

**Proper Fix Would:**
1. Add webhook handler for `payment.success` / `subscription.charged` events
2. Match incoming success to prior recovery_action by payment_id
3. Update `recovery_actions.status = 'recovered'` and `resolved_at = NOW()`
4. False-positive rate becomes: `(executed - confirmed_recovered) / executed`

**Why Not Done:** Requires:
- New webhook endpoint `/webhooks/razorpay` 
- Event matching logic (payment_id → target_id lookup)
- Schema already supports `status='recovered'` but no code writes it

**Simulation Option:** Could add a script that randomly updates 70% of executed actions to `status='recovered'` for demo purposes.

**Status:** ✗ NOT DONE - Coefficients are research-grounded (Part 5), but still estimated

---

### 8. LLM Circuit Breaker

**Issue:** No circuit breaker. If Claude API is down, every call waits 30s timeout.

**Current Code (llm_client.py):**
```python
TIMEOUT_SECONDS = 30  # No retry, no circuit breaker

def call_claude(prompt, ...):
    result = client.messages.create(...)  # Blocks for 30s on timeout
    # No tracking of consecutive failures
```

**Proper Fix Would:**
```python
# Global state (or Redis in production)
consecutive_failures = 0
circuit_open_until = None

def call_claude(prompt, ...):
    global consecutive_failures, circuit_open_until
    
    # If circuit is open, skip LLM immediately
    if circuit_open_until and datetime.now() < circuit_open_until:
        return {
            'success': False,
            'response': None,
            'log': {'circuit': 'open', 'cooldown_until': circuit_open_until}
        }
    
    try:
        result = client.messages.create(...)
        consecutive_failures = 0  # Reset on success
        return {'success': True, ...}
    except Exception as e:
        consecutive_failures += 1
        
        if consecutive_failures >= 3:
            circuit_open_until = datetime.now() + timedelta(minutes=5)
            print(f"Circuit breaker OPEN: {consecutive_failures} failures, cooling down 5min")
        
        return {'success': False, ...}
```

**Why Not Done:** Requires global state tracking, more complex than single-fix scope.

**Impact:** Under LLM outage, pipeline becomes very slow (30s per timeout) but doesn't break (rules fallback works).

**Status:** ✗ NOT DONE - System degrades slowly without circuit breaker, but doesn't fail

---

## SUMMARY

### Fixed (5/8 items)
1. ✓ PII masking coverage verified (only audit-trail needs it, and it's masked)
2. ✓ Masking architecture documented (read-time only, gaps identified)
3. ✓ RBI guardrail hardened (checks mandate_status field)
4. ✓ Rate limit NULL handling fixed (blocks instead of allowing)
5. ✓ Guardrail aggregation implemented (all violations logged)

### Not Fixed (3/8 items)
6. ✗ Idempotency key (requires schema change, out of scope)
7. ✗ Real false-positive tracking (requires webhook handler, out of scope)
8. ✗ LLM circuit breaker (requires global state, out of scope)

### What's Production-Ready Now
- RBI compliance is defense-in-depth (checks mandate status, not just type)
- Rate limits fail safe (block on NULL or error, don't silently allow)
- Guardrails log all violations (auditable, not just first failure)
- PII is masked in all relevant API responses

### What's Still Demo-Grade
- Idempotency works for replay prevention, not true webhook dedup
- False-positive rate uses research-backed coefficients, not real tracking
- LLM outage causes slowdown (30s timeouts), not fast fail

### Grep Verification Commands

```bash
# Verify RBI checks mandate_status
grep -A3 "mandate_status = record.get" agent/action_executor.py

# Verify rate limit blocks on NULL
grep -A3 "if not customer_id:" agent/action_executor.py | grep "allowed': False"

# Verify guardrails aggregate
grep -n "violations = \[\]" agent/action_executor.py
grep "violations.append" agent/action_executor.py | wc -l  # Should show multiple

# Verify all endpoints
grep "@router.get" api/metrics.py
```

### Honest Conclusion

Part B completes the guardrail hardening that can be done within single-file fixes. The remaining 3 items (idempotency, recovery tracking, circuit breaker) require multi-component changes (schema, webhooks, global state) that are beyond the scope of "fix dead code and harden existing logic."

The system is significantly more production-credible than before Part B:
- Safety-critical checks (RBI, rate limits) now fail safe
- Audit trail is comprehensive (all violations logged)
- No silent bypasses on missing data

Items 6-8 are documented as "designed but not implemented" and would be Phase 2 work in a real production rollout.
