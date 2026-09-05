# Fix Prompt — Part C of 3: Production-Ops Basics & Testing

This is Part C of a 3-part fix. Prerequisite: Parts A and B complete and their
completion reports show real, verified fixes — confirm before starting this
part.

Continue treating every prior "complete" claim as unverified until you
personally confirm it with evidence.

## 0. Carried Over From Part B (Do These First)

Part B correctly identified these three as legitimate multi-component work
rather than falsely marking them done — that honesty is good, but they still
need to actually get built. They fit here because Part C is already doing
schema/infra-level changes (connection pooling, health checks), so do these
alongside that work:

- **Proper webhook deduplication (originally item 6).** Add an `event_id`
  column to `recovery_actions` via a real migration (not an ad hoc `ALTER
  TABLE` with no record of it), populate it from the Razorpay webhook
  payload, and key the duplicate check on `event_id` rather than
  `target_id` + time window alone.
- **Real false-positive tracking (originally item 9).** This needs the
  success-side webhook handler flagged in Part B (`payment.captured`,
  `subscription.charged`) actually implemented: on receipt, match the
  event to its `recovery_actions` row and set `status='recovered'`. Wire
  this into the same webhook receiver being hardened in this part (see
  Section on `/health` and logging below) rather than as a separate
  one-off endpoint. Update the false-positive rate to use the confirmed
  count as primary, clearly labeled `"source": "confirmed"` vs
  `"source": "estimated"` in the API response — not just in comments.
- **LLM circuit breaker (originally item 10).** Add simple global state to
  `llm_client.py` — track consecutive failures in memory, and after N
  (e.g. 3) in a row, skip the LLM entirely for a cooldown window (e.g. 60s)
  and go straight to the rules-based fallback. This doesn't need to be
  elaborate; an in-memory counter and timestamp is sufficient for this
  scale — don't reach for an external library for this.

## Production-Ops Basics (implement, don't just note as "future work")

11. Replace `print()` statements with the standard `logging` module,
    structured with severity levels and a correlation ID that follows one
    event through detection → diagnosis → decision → action → outcome.

12. Add connection pooling to `database.py` (e.g. `psycopg2`
    `ThreadedConnectionPool`) instead of opening a fresh connection per call.

13. Add a real `/health` check that verifies DB and LLM API reachability, not
    just a static `{"status": "healthy"}`, plus a basic `/metrics` endpoint
    exposing action counts, guardrail-block counts, and latency.

14. Add a simple API key check to `backend/api/metrics.py` endpoints — even a
    single shared header check is enough to answer "is this secured" honestly.

15. Add frontend error states in `page.tsx`: show a visible failure message
    and a retry action if the backend is unreachable, instead of an infinite
    loading spinner.

## Testing

16. Expand `seed_data.py` edge cases beyond the single NULL `failure_reason`:
    duplicate `event_id`, out-of-order status transitions, NULL
    `mandate_status`, `abandoned_at` set with inconsistent `stage_reached`,
    and boundary amounts (zero, negative, very large). Confirm the pipeline
    handles each without crashing or producing an incorrect action.

17. Add one true integration test that runs a record through the full
    pipeline into the database and confirms the dashboard API reflects it
    correctly — not just unit tests of individual functions.

## Verification Requirement

For each fix above, provide the evidence a skeptical reviewer would need: the
exact grep/search, log output, or test run proving the behavior — not a prose
description of intent. If something genuinely can't be finished, say so
explicitly rather than marking it complete.

## Final Report

Produce `PARTC_COMPLETE.md`, and also a consolidated `FINAL_REVIEW.md` covering
all three parts together:
- Flaws found and fixed, each with before/after evidence
- What's still a known limitation and why
- What remains genuinely production-credible versus what's still
  hackathon-scoped by necessity, stated honestly rather than glossed over
