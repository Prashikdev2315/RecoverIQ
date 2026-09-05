# AI Revenue Recovery Agent - Demo Script

## Setup Before Demo

1. **Backend running**: `cd backend && python main.py` (port 8000)
2. **Frontend running**: `cd frontend && npm run dev` (port 3000)
3. **Database seeded**: `python backend/seed_data.py`
4. **Pipeline run**: `python backend/run_pipeline_on_seed.py` (generates Hinglish examples)
5. **Browser open**: `http://localhost:3000`

## Demo Flow (5-7 minutes)

### 1. Hook (30 seconds)

**Say:**
> "Every merchant loses revenue silently. A payment fails at 2am, a customer abandons their cart, a subscription stops charging—and nobody notices until it's too late. We built the AI agent that catches these leaks, figures out why they happened, and wins that money back automatically."

**Show:** Dashboard homepage loading

---

### 2. The Problem (30 seconds)

**Say:**
> "Here's what we're looking at: [point to stats cards] over 200 failed transactions, 80+ abandoned checkouts, 50 failed subscriptions from our test data. That's real money at risk—₹X lakhs just sitting there."

**Show:** Overview tab, stats cards

---

### 3. The Solution - Live Flow (2 minutes)

**Say:**
> "Let's watch the agent work. I'll trigger the pipeline on a failed payment."

**Do:** Run in terminal visible to judges:
```bash
python backend/run_pipeline_on_seed.py 5
```

**Show terminal output:**
- Detection phase ("Classified as transaction, severity: high")
- Diagnosis phase ("Diagnosis: insufficient_funds, method: rules")
- Decision phase ("Proposed action: send_payment_link, confidence: 0.82")
- Execution phase ("Status: executed")

**Say:**
> "Notice three things: First, it used rule-based logic for this clear-cut case—fast and deterministic. Second, the confidence score is 82%, which matters for our false-positive rate. Third, every decision is logged with full reasoning."

**Switch to browser:**
> "And here it is in the dashboard—refresh—new entry in the audit trail."

**Click "View" on any entry**

**Say:**
> "This is the full reasoning log. Everything the agent saw, every decision it made, why it chose this action. This is what makes it auditable for compliance."

---

### 4. The Differentiator - Hinglish (1 minute)

**Click "Hinglish Messages" tab**

**Say:**
> "This is our standout feature. Indian merchants don't message customers in formal English—they use Hinglish. Natural code-mixing, the way people actually talk."

**Point to side-by-side examples:**
> "Same message, two ways. The Hinglish version gets better engagement because it feels personal, not corporate. And this runs by default—70% of messages are generated in Hinglish automatically, 30% English, mimicking real merchant behavior."

**Say:**
> "Every message also passes a compliance filter. No threats, no false urgency, no legal language. If the AI generates something aggressive, it regenerates automatically until it's compliant."

---

### 5. Industry-Ready Proof (1.5 minutes)

**Back to Overview tab**

**Point to False Positive Rate:**

**Say:**
> "This is computed from real data, not hardcoded. [Read the percentage]. We show this honestly because every recovery system has wasted actions. Hiding it looks worse than a real number."

**Point to Guardrail Enforcement section:**

**Say:**
> "Here's proof the system is bounded. [Read blocked count] actions were blocked by guardrails. SMS rate limits, retry caps, fraud detection—all enforced before any action executes."

**Click to expand guardrail reasons if available:**
> "You can see exactly why: exceeded daily cap, confidence too low, suspected fraud pattern. The agent proposes, but guardrails enforce. That's the separation that makes this production-ready."

**Point to Funnel:**
> "And here's the business impact: [Read recovery rate]% of at-risk revenue recovered. That's real pipeline runs against real test data."

---

### 6. Break It On Purpose (1 minute)

**Say:**
> "Let me show you what happens when things go wrong. We injected a malformed record in the seed data—a failed transaction with no failure reason."

**Do:** Run in terminal:
```bash
python backend/test_failure_scenario.py
```

**Show output:**
- "System did not crash"
- "Anomaly logged in audit trail"
- "No duplicate action created"

**Switch to browser, Audit Trail tab:**
> "Here it is—the system caught it, logged it, handled it gracefully. No crash, no silent failure, no duplicate charge. This is the kind of reliability demo that matters in production."

---

### 7. Close (30 seconds)

**Say:**
> "To recap: We built an AI revenue recovery agent that's bounded, explainable, and auditable. It runs on real Razorpay test-mode integration—this isn't a mock. Every number you saw came from actual database queries. Every decision is logged. And it speaks the language merchants actually use."

**Say:**
> "Built from scratch in 4 days—no templates, no agent frameworks, just clean code solving a real problem. Thank you."

---

## Backup Answers for Judge Questions

### "How do you prevent double-charging?"

> "Two layers: First, idempotency with a 5-minute window—replay attacks are blocked. Second, retry limits enforced at the guardrail level—max 3 attempts, and we never retry expired cards or suspected fraud. You can see the blocked actions in the dashboard."

### "What if the LLM is down?"

> "Every LLM call has a timeout and rules-based fallback. For diagnosis, we fall back to 'unknown failure, escalate to human.' For message generation, we use hardcoded safe templates. The system degrades gracefully, it doesn't break."

### "Is the false-positive rate really computed or hardcoded?"

> "It's computed from actual confidence scores in the database. High-confidence actions get a 75% estimated success rate, medium 55%, low 30%. The math is in the code—we can show you the query."

### "Does Hinglish actually run by default?"

> "Yes. We changed the language selection logic to generate 70% Hinglish, 30% English by default. No manual toggle needed. Run the pipeline now and you'll see Hinglish messages appear automatically."

### "How do you handle webhook signature verification?"

> "Every webhook verifies the X-Razorpay-Signature header using HMAC-SHA256 before processing. We have a test that confirms tampered payloads are rejected. The code is in main.py."

### "Did you use any templates or boilerplates?"

> "No. We used create-next-app for bare Next.js scaffolding, then deleted all placeholder content and built the dashboard from scratch. Backend is pure Python—no LangChain, no agent frameworks. Every component is original."

---

## What to Have Ready

- Terminal 1: Backend running
- Terminal 2: Frontend running  
- Terminal 3: Ready to run tests/pipeline
- Browser: Dashboard at localhost:3000, Overview tab
- Code editor: Open to show specific files if asked

## Timing Notes

- Keep hook under 30 seconds
- Spend most time (2-3 min) on the live flow and Hinglish
- The "break it" demo is the most convincing thing—rehearse it
- Leave 1-2 minutes for questions
