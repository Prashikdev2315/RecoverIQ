# PROJECT_STATE_FOR_DEMO.md

> **How to read this file:** Every fact is sourced from a live API query or direct code read
> performed at 20:17–20:20 IST, 2026-09-05. Nothing here is recalled from memory or design docs.
> Verified-live facts are marked **[LIVE]**. Code-verified facts are marked **[CODE]**.
> Known limitations are stated plainly in section 6.

---

## 1. ONE-LINE PITCH

An agentic AI pipeline that automatically triages failed Razorpay payments, abandoned checkouts,
and failed subscription mandates — classifies the root cause, decides the right recovery action,
enforces guardrails so it can't harm customers, and logs every decision with full reasoning for
audit — all in under 4 milliseconds per record.

---

## 2. THE PROBLEM AND WHY THIS TRACK (Track 03 — AI Revenue Recovery)

**What Track 03 asked for:** An AI system that detects and recovers revenue from failed
payments in the Razorpay ecosystem, with awareness of Indian regulatory constraints
(RBI e-mandate rules) and Indian customer context (language, payment method mix).

**What this project addresses:**
- Three failure modes are covered: failed card/UPI/netbanking transactions, abandoned checkout
  sessions (at any funnel stage: cart / payment page / OTP), and failed subscription mandate charges.
- The pipeline is fully automated end-to-end: detect → diagnose → decide → execute → audit.
  No human is needed in the loop unless the system's guardrails say confidence is too low.
- RBI e-mandate compliance is enforced programmatically — the system cannot retry a subscription
  mandate directly, period, regardless of what the upstream classifier recommends.
- Customer communications are in Hinglish (Hindi+English code-mix), which is the natural
  register for urban Indian payment recovery messages.

---

## 3. ARCHITECTURE OVERVIEW

The pipeline lives in `backend/agent/` and runs in five sequential steps for every record.

### Step 0 — Reconciliation (fail-closed)
**[CODE: pipeline.py lines 11–115]**
Before doing anything, the pipeline re-reads the current status of the record from the database.
If the payment has since succeeded, been refunded, or the checkout completed, the pipeline aborts
immediately without writing anything. If the database itself errors, the pipeline also aborts —
it fails closed, not open. This prevents double-actions on records that resolved between trigger and processing.

### Step 1 — Detector (`detector.py`)
**[CODE: detector.py]**
Classifies the incoming record as one of three event types (transaction / checkout_session /
subscription) and assigns a severity (low / medium / high / critical) based on amount thresholds
and retry history. For example: a failed transaction ≥ ₹1,000 with 2+ retries is CRITICAL;
a first-attempt failure under ₹100 is LOW. This severity feeds into downstream decisions
and channel selection.

### Step 2 — Diagnoser (`diagnoser.py`)
**[CODE: diagnoser.py]**
Determines the root cause using a rules-first approach: it normalises the raw failure reason string
against an internal error taxonomy (`error_taxonomy.py`) to a canonical category
(e.g. HARD_INSUFFICIENT_FUNDS, HARD_CARD_EXPIRED, SOFT_BANK_GATEWAY_ERROR). Each canonical
category maps to a recoverability flag and a recommended action hint. For ambiguous cases the
diagnoser is wired to call Claude via `llm_client.py`, but currently falls back to rules because
the Anthropic API key is not valid in this environment — all 190 actions in the live dataset
were diagnosed using rules (confirmed in audit trail `"method": "rules"`).

### Step 3 — Decision Engine (`decision_engine.py`)
**[CODE: decision_engine.py]**
Maps the diagnosis hint to a concrete action from a fixed catalog:
`send_reminder_sms | send_payment_link | retry_charge | offer_alternate_method | escalate_to_human | no_action`.
Confidence is calculated from a base score per action type, modified by diagnosis confidence.
**RBI enforcement happens here first:** if the target is a subscription and the proposed action
is `retry_charge`, the engine overrides it to `send_payment_link` unconditionally.
Channel (SMS / payment_link / email) and language (70% Hinglish / 30% English, randomly
assigned to simulate a real customer mix) are also decided here.

### Step 4 — Action Executor (`action_executor.py`)
**[CODE: action_executor.py]**
Runs six guardrail checks in sequence before executing. If any check fails, the action is blocked
and the full violation list is logged. The checks are:

1. **RBI mandate guardrail** — if subscription + retry_charge, blocked unconditionally for ALL
   mandate_status values (active, paused, pending, NULL, cancelled). Defense-in-depth: this
   check runs even if decision_engine somehow let it through.
2. **Confidence threshold** — minimum 0.6; below that, escalates to human.
3. **Fraud detection** — blocks if customer has 3+ failures across 3+ different payment methods
   in 24 hours.
4. **Duplicate event check** — primary: by Razorpay `event_id` (24-hour window); fallback: by
   `(target_type, target_id)` within a 5-minute window.
5. **SMS rate limit** — max 2 SMS per customer per day.
6. **Payment link limit** — max 3 payment links per transaction.

If all checks pass, `perform_action()` is called. **All actions are currently simulated** —
`execution_log['simulated'] = True` — no actual SMS is sent, no Razorpay API call is made.

### Step 5 — Audit Logger (inside `pipeline.py`)
**[CODE: pipeline.py log_recovery_action()]**
Writes a complete reasoning trail to `recovery_actions` table, including: classification,
diagnosis, decision, execution result, all guardrail violations, the Hinglish message generated
(if applicable), and real wall-clock processing duration via `time.perf_counter()`.
The `processing_duration_seconds` column is what the latency metric reads — not timestamps.

---

## 4. STANDOUT FEATURES

### A. RBI-Compliant Mandate Handling
**Why it matters:** Programmatic back-to-back mandate retries are a compliance violation under
India's RBI e-mandate framework, which requires a 24-hour pre-debit notification before any
auto-debit. A naive recovery system that just retries could expose a fintech to regulatory action.

**Current real status — WORKING, ENFORCED AT TWO LAYERS:**
- `decision_engine.py` line 93-95: subscription + retry_charge → overridden to `send_payment_link`
  before the action even reaches the executor.
- `action_executor.py` lines 46-97: executor blocks retry_charge for ALL mandate_status values
  (active, paused, pending, NULL, cancelled) with a separate DB-level check.
  This is explicitly called "defense-in-depth" in the code comments.
- **[LIVE]** In the current dataset: 0 direct retry_charge actions on subscriptions. All 12
  subscription actions resolved to `send_payment_link` or `escalate_to_human`.

---

### B. Hinglish Recovery Messaging (Two-Path System)
**Why it matters:** Urban Indian customers respond significantly better to Hinglish messages than
formal English in payment recovery contexts. Template-first keeps the system TRAI/WhatsApp compliant.

**Current real status:**
- **Template path (initial messages):** Working. `message_generator.py` lines 80-87: initial
  messages use pre-approved templates with variable slots (`{name}`, `{amount}`, `{issue}`, `{url}`).
  Template is 60-70% static text, matching Meta/WhatsApp Business API requirements.
- **LLM path (follow-ups):** Coded and wired (`generate_with_llm()` in `message_generator.py`),
  but **not currently triggerable** — the pipeline always passes `is_follow_up=False`
  (line 387 of message_generator.py: `# Always use template for initial messages`). Additionally,
  the Anthropic API key is invalid, so LLM calls return 401 errors. The fallback message fires
  instead. The LLM path is infrastructure-ready but not demo-live.

**Real template example from live API [LIVE, from /api/metrics/hinglish-examples at 19:55 IST]:**
```
Action: send_reminder_sms | Customer: Rohan
Hinglish: "Namaste Rohan, aapka ₹1999.00 ka payment pending hai.
           Issue: Payment mandate not yet. Kripya payment complete karein: [Payment Link]"
English:  "Hello Rohan, your payment of ₹1999.00 is pending.
           Issue: Payment mandate not yet. Please complete payment: [Payment Link]"
Character count: 132 | generation_method: template
```

A compliance filter (`check_compliance()`) runs on every generated message and rejects messages
containing legal threats, debt collection language, shaming language, or promotional offers.

---

### C. Guardrail System
**Why it matters:** An autonomous payment recovery system that sends without limits is a
spam/harassment liability. The guardrails enforce that the system is bounded.

**Current real status — FULLY WORKING [LIVE, from /api/metrics/guardrail-hits at 20:17 IST]:**
- Total blocked: **40 of 190 actions** (21% block rate)
- Top 3 block reasons with real counts:
  1. **SMS rate limit hit** (`send_reminder_sms` blocked): **15 blocks** — "Customer already
     received 2 SMS today (limit: 2)"
  2. **Same-method failure check** (`offer_alternate_method` blocked): **10 blocks** — "Only 0
     failure(s) on card/wallet/netbanking (need 2+)" — the system won't offer an alternate method
     unless there's evidence the current method repeatedly fails for this customer.
  3. **Confidence threshold** (`offer_alternate_method` blocked): **5 blocks** — "Confidence 0.55
     below threshold 0.6 | Missing customer or payment method"
  4. **Fraud detection** (multi-method failures): **3 blocks** — "3 failures across 3 payment
     methods in 24h"

---

### D. DPDP-Aligned PII Masking
**Why it matters:** India's Digital Personal Data Protection Act 2023 requires data minimisation
at the processing boundary. Logging full UUIDs, phone numbers, or card numbers in readable
audit trails is a liability.

**Current real scope [CODE: utils.py + metrics.py]:**
- **What's masked:** customer_id (→ first-4/XXXX/last-4), phone numbers (→ +91-XXXXX-XXXX),
  email addresses (→ first-2-chars***@domain), card numbers (→ XXXX-XXXX-XXXX-last-4).
- **Where it's applied:** READ-TIME only. The `sanitize_for_logging()` function is called in
  `metrics.py` on the `reasoning_log` JSON blob before serving it through the `/api/metrics/audit-trail`
  endpoint. Raw UUIDs are stored unmasked in the database.
- **What's NOT done:** Write-time masking in the DB, field-level encryption, consent management,
  or erasure workflows. The current implementation is a display-layer filter, not a full DPDP
  data lifecycle implementation.

---

### E. Reconciliation Check (Fail-Closed)
**Why it matters:** Webhook-triggered systems face the "duplicate delivery" problem — a payment
that succeeds moments after the webhook fires could be double-acted on. Fail-closed reconciliation
prevents that.

**Current real status — WORKING [CODE: pipeline.py lines 11-115]:**
- Step 0 of every pipeline run re-queries the current record status from the DB.
- If transaction moved to `success` or `refunded` → pipeline aborts.
- If checkout moved to `completed` → pipeline aborts.
- If subscription moved to `active` → pipeline aborts.
- If the DB query itself throws an exception → pipeline aborts (fail-closed).
- This is separate from the duplicate event dedup check in the action executor (which uses
  `event_id` or a 5-minute `target_id` window).

---

## 5. CURRENT REAL METRICS

*All numbers pulled from live API at 20:17 IST, 2026-09-05, after full seed + pipeline run.*
*Source records: 354 total (212 transactions + 87 checkout sessions + 55 subscriptions).*

| Metric | Value | Measurement Type |
|--------|-------|-----------------|
| **Total recovery actions logged** | 190 | **Measured live** — DB count |
| **Executed actions** | 150 | **Measured live** |
| **Blocked by guardrails** | 40 | **Measured live** |
| **At-risk revenue** | ₹5,10,949.53 | **Measured live** — sum of failed amounts |
| **Estimated recovered** | ₹1,02,875.68 | **Research-estimate** — 30% of executed-action amounts |
| **Recovery rate** | 20.13% | **Research-estimate** — uses published Razorpay/Stripe recovery benchmarks |
| **False-positive rate** | 38.67% | **Research-estimate** — "Estimated using research-based coefficients (0.75 high, 0.55 medium, 0.30 low)" |
| **Confirmed recovered** | 0 | **Measured** — requires real `payment.captured` webhooks |
| **Avg. pipeline latency** | 3.5 ms | **Measured live** — `processing_duration_seconds` column, 190 actions |
| **Min latency** | 0.7 ms | **Measured live** |
| **Max latency** | 410.6 ms | **Measured live** (outlier; typical <5ms) |

**Recovery breakdown by source type [LIVE]:**
- Failed transactions: 127 actions, 107 executed, 20 blocked, 20.0% estimated recovery
- Abandoned checkouts: 51 actions, 37 executed, 14 blocked, 21.63% estimated recovery
- Failed subscriptions: 12 actions, 6 executed, 6 blocked, 16.29% estimated recovery

**Top 3 guardrail-hit reasons [LIVE]:**
1. SMS rate limit (2/day) — 15 blocks
2. Same-method failure threshold not met — 10 blocks
3. Confidence below 0.6 — 5 blocks

**Important caveat on financial numbers:** The "estimated recovered" and "recovery rate" figures
use industry benchmark coefficients from Razorpay/Stripe research (0.75 for high-confidence,
0.55 for medium-confidence actions). No actual payment was completed in this demo — the system
executed no real Razorpay API calls and sent no real SMS messages.

---

## 6. KNOWN LIMITATIONS

These are stated as an engineer would describe them to a technically sharp judge.

### Running on Seed Data, Not Real Webhooks
The entire demo runs against seed data generated by `seed_data.py`. The 354 records have
deliberately backdated `created_at` timestamps (ranging from 2026-08-11 to 2026-09-05) to
simulate a realistic history. The Razorpay webhook endpoint (`POST /webhooks/razorpay`) exists
and validates HMAC signatures, but no real Razorpay webhook fired during this demo session.

### No Actual Actions Executed
`action_executor.perform_action()` sets `simulated: True` in all execution logs. No SMS was sent.
No Razorpay payment link was created. No charge was retried. The pipeline decides and logs what
it *would* do — it does not make the external API call.

### LLM (Claude) Not Wired
The diagnoser and message generator both have LLM paths that call Claude via `llm_client.py`.
The Anthropic API key configured in `.env` returns 401 Unauthorized. All 190 actions in the
current dataset used rules-based diagnosis. The LLM follow-up message path in `message_generator.py`
also cannot currently fire (the pipeline always calls with `is_follow_up=False`).

### False-Positive / Recovery Rate Are Estimates, Not Measured
The `/api/metrics/false-positive-rate` response explicitly says `"data_source": "estimated"`.
Actual recovery tracking requires `payment.captured` and `subscription.charged` webhooks from
Razorpay to confirm which customers actually paid after the recovery action. That plumbing
is not connected.

### PII Masking Is Display-Layer Only
The DPDP masking in `utils.py` applies at read-time on the audit trail API endpoint only.
Customer IDs, amounts, and failure reasons are stored raw in PostgreSQL. There is no field-level
encryption, no write-time redaction, and no erasure/right-to-be-forgotten workflow.

### No Integration Tests or CI
There is no automated test suite that runs against the live pipeline. The `run_pipeline_on_seed.py`
script serves as a manual integration test (run it, check summary), but there are no unit tests
for individual pipeline stages and no CI/CD pipeline that runs them on push.

### Structured Logging Is Partially Wired
`logging_config.py` and `get_logger()` are imported in the pipeline, but most pipeline output
goes to stdout via `print()` statements. The structured log correlation ID system is
infrastructure-ready but not used consistently.

### Frontend Is a Read-Only Dashboard
The Next.js frontend at `localhost:3000` reads from the metrics API and displays data.
It has no write path — you can't trigger pipeline runs, adjust guardrail thresholds, or
send a recovery action from the UI.

---

## 7. WHAT A JUDGE CAN ACTUALLY CLICK THROUGH

The frontend at `http://localhost:3000` has three tabs:

### Tab 1 — Overview
Shows the core funnel metrics: at-risk revenue, actions taken, amount recovered, recovery rate,
and a breakdown by category (transactions / checkouts / subscriptions). Also shows:
- Response latency (currently: 3.5ms average — this is real pipeline timing, not a fake number)
- False-positive rate (currently: 38.67% — labelled as estimated)
- Guardrail hits count

**Genuine demo moment:** The latency number. It used to show "10.8 days" because the query
compared `recovery_action.created_at` against backdated seed timestamps. That was a real bug,
found in production, fixed with a verified before/after API comparison. The 3.5ms number is
real wall-clock time from `time.perf_counter()`.

### Tab 2 — Hinglish Messages
Shows the Hinglish messages generated during the last pipeline run, with the English equivalent
and character count side-by-side. Currently all shown messages are template-generated
(generation_method: template). Customer names are real names from the seed data
(Rohan, Vikram, Divya, Aarav, Ananya, etc.) — not "Valued Customer".

**Genuine demo moment:** The name fix. The messages previously showed "Namaste Customer" across
all entries because `customer_name` was hardcoded in the pipeline. That was a real bug caught
by verifying the actual API response, not by reading the code. It's fixed and the names are now
real.

### Tab 3 — Audit Trail
Shows the full reasoning log for each pipeline action: what was detected, what was diagnosed,
what action was proposed, whether guardrails blocked it and why, and the final executed action.
Customer IDs are masked (first-4/XXXX/last-4) in the display.

**Genuine demo moment:** Open any guardrail-blocked entry. The reasoning_log shows all violations
found — not just the primary one. For example, an `offer_alternate_method` action blocked due to
"Confidence 0.55 below threshold 0.6 | Missing customer or payment method" shows both the
confidence issue and the missing data issue in the same log entry.

### Live Test Scripts (runnable during demo)
All three of these work right now from the `backend/` directory:

```bash
# Run the full pipeline again on fresh seed data (takes ~12 seconds for 354 records)
$env:PYTHONIOENCODING="utf-8"; python seed_data.py; python run_pipeline_on_seed.py

# Check current DB state — row counts, sample names, latency data
$env:PYTHONIOENCODING="utf-8"; python check_tables.py
$env:PYTHONIOENCODING="utf-8"; python check_latency.py
```

---

## 8. THE STRONGEST, MOST DEFENSIBLE TALKING POINTS

These are things that held up through multiple rounds of real testing and would survive a
follow-up question from a technically sharp judge.

### 1. The RBI e-mandate rule is enforced at two independent layers
If a judge asks "what stops this from violating RBI rules on mandate retries?" — the answer is:
it's blocked at both the decision layer (`decision_engine.py` line 93: override subscription +
retry_charge → send_payment_link) AND at the executor layer (`action_executor.py` lines 46–97:
unconditional block for all mandate_status values including NULL and cancelled). The code comment
explicitly says "defense-in-depth." No subscription in the 190-action dataset has a
`retry_charge` logged. This is verifiable by querying the DB right now.

### 2. The latency metric is honest about what it measures
If a judge asks "3.5ms seems suspiciously fast for a real system" — the answer is accurate:
this is the wall-clock time for the Python pipeline code to run on a local machine against a
local PostgreSQL DB, measured by `time.perf_counter()`. It doesn't include network latency,
webhook processing time, or any external API calls (since those are simulated). The
`data_source: "processing_duration_seconds"` field in the API response documents this precisely.
The earlier bug where it showed "10.8 days" was a backdated-timestamp artifact, and the fix
involved replacing the query with one that reads the actual timing column.

### 3. The guardrail system is genuinely bounded — and the numbers prove it
40 of 190 actions (21%) were blocked by guardrails. The top block reason (SMS rate limit, 15
blocks) demonstrates that the system naturally limits customer contact even when the classifier
recommends an action. A judge can query `/api/metrics/guardrail-hits` live and see the real
breakdown with counts. The blocking is not theoretical — it happened in this run.

### 4. Every number on the dashboard has a traceable source and honest labelling
The recovery rate (20.13%) and false-positive rate (38.67%) are labelled "estimated" in the
API response because they use published industry benchmarks, not actual payment captures.
The `confirmed_recovered: 0` field is explicitly present in the false-positive-rate response,
and the note explains what would be needed to measure it for real (payment.captured webhooks).
This is the kind of intellectual honesty that distinguishes a real system from a demo that
inflates its numbers.

---

*Document generated: 2026-09-05 20:20 IST*
*Live data source: localhost:8000 (FastAPI + PostgreSQL), 190 recovery actions, full seed dataset*
*Code read from: c:\Users\dell\Desktop\Razorpay\backend\*
