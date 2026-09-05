# AI Revenue Recovery Agent

**Razorpay Buildathon - Track 03: AI-Powered Revenue Recovery**

An intelligent agent that detects revenue leaks (failed payments, abandoned checkouts, failed subscriptions), diagnoses root causes, and executes recovery actions automatically—with strict guardrails and full audit trails.

## Key Features

- **Intelligent Detection**: Classifies issues by type and severity using rules-based logic
- **Root Cause Analysis**: Rules-first diagnosis with LLM fallback for ambiguous cases
- **Hinglish Messaging**: Natural Hindi+English code-mixed recovery messages (70% default)
- **Strict Guardrails**: Rate limits, retry caps, confidence thresholds, fraud detection
- **Full Auditability**: Every decision logged with complete reasoning
- **Industry-Ready**: Idempotent, compliant, handles failures gracefully

## Architecture

```
Razorpay Test Mode → Webhook Receiver → Pipeline (Detector → Diagnoser → Decision Engine → Action Executor)
                                           ↓
                                    Recovery Actions (Audit Log)
                                           ↓
                                    Dashboard (Next.js)
```

## Project Structure

```
.
├── backend/
│   ├── agent/
│   │   ├── detector.py          # Event classification by type and severity
│   │   ├── diagnoser.py         # Root cause analysis (rules + LLM)
│   │   ├── decision_engine.py   # Maps diagnosis to action catalog
│   │   ├── action_executor.py   # Enforces guardrails before execution
│   │   ├── llm_client.py        # Claude API wrapper
│   │   └── pipeline.py          # Orchestrates the full pipeline
│   ├── main.py                  # FastAPI application with webhook receiver
│   ├── database.py              # Database connection utilities
│   ├── schema.sql               # PostgreSQL schema
│   ├── seed_data.py             # Seed data generator
│   ├── run_pipeline_on_seed.py  # Batch pipeline runner
│   ├── test_idempotency.py      # Idempotency tests
│   └── requirements.txt         # Python dependencies
├── .env.example                 # Environment variables template
├── Part1_Foundation_and_Data.md
└── Part2_Agent_Core_and_Guardrails.md
```

## Quick Start

### Prerequisites

- Python 3.8+
- Node.js 18+
- PostgreSQL 14+
- Razorpay test account (optional for webhook testing)
- Anthropic API key

### 1. Database Setup

```bash
createdb revenue_recovery
psql revenue_recovery < backend/schema.sql
```

### 2. Environment Configuration

```bash
cp .env.example .env
# Edit .env and add your credentials
```

Required environment variables:
- `DATABASE_URL` - PostgreSQL connection string
- `ANTHROPIC_API_KEY` - Your Anthropic API key for Claude
- `RAZORPAY_KEY_ID` - Your Razorpay test key ID (optional)
- `RAZORPAY_KEY_SECRET` - Your Razorpay test key secret (optional)
- `RAZORPAY_WEBHOOK_SECRET` - Your webhook secret (optional)

### 3. Install Dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 4. Generate Seed Data

```bash
cd backend
python seed_data.py
```

### 5. Run the Recovery Pipeline

```bash
python run_pipeline_on_seed.py
```

This processes all seed data and generates recovery actions (including Hinglish messages).

### 6. Start the Application

**Terminal 1 - Backend:**
```bash
cd backend
python main.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

**Access the dashboard:** http://localhost:3000

## Testing

```bash
cd backend

# Test idempotency (duplicate blocking + legitimate retries)
python test_idempotency.py

# Test webhook signature verification
python test_webhook_security.py

# Test compliance filter
python test_compliance.py

# Test edge case handling
python test_failure_scenario.py
```

```bash
python main.py
```

## Features Deep Dive

### Hinglish Messaging (Standout Feature)

The system generates natural Hindi+English code-mixed messages by default:

- **70% Hinglish, 30% English** - Automatic language selection without manual configuration
- **Compliance-filtered** - All messages checked for forbidden phrases (legal threats, false urgency, shaming)
- **Auto-regeneration** - If a message fails compliance, system regenerates with stricter guidelines
- **Under 160 chars** - Optimized for SMS delivery

**Example:**
- Hinglish: "Namaste Rahul, aapka ₹500 ka payment pending hai. Kripya check karein."
- English: "Hello Rahul, your payment of ₹500 is pending. Please check."

### Guardrails

All enforced deterministically before execution:

- **SMS Rate Limiting**: Max 2 per day per customer
- **Payment Link Limits**: Max 3 per transaction
- **Retry Limits**: Max 3 per subscription
- **Confidence Threshold**: Min 0.6 to auto-execute
- **Fraud Detection**: Multiple payment methods failing = escalate to human
- **Idempotency**: 5-minute window prevents webhook replay attacks

### Decision Engine

Fixed action catalog (never invents actions):
- `send_reminder_sms` - For abandonments
- `send_payment_link` - For recoverable failures
- `retry_charge` - For transient subscription issues
- `offer_alternate_method` - After repeated same-method failures
- `escalate_to_human` - For low confidence or fraud
- `no_action` - When genuinely unrecoverable

### Audit Trail

Every decision includes:
- Classification (type, severity, fraud indicators)
- Diagnosis (root cause, method used, confidence)
- Decision reasoning (action, confidence score, channel)
- Execution result (status, guardrail blocks, messages sent)
- Full LLM prompts/responses (when used)

## Dashboard

Single-page design with 3 tabs:

1. **Overview**: Funnel, recovery rates, false-positive rate, latency, guardrail hits
2. **Hinglish Messages**: Side-by-side examples with character counts
3. **Audit Trail**: Clickable table with full reasoning logs

All metrics computed from real database queries, no hardcoded values.

## Built From Scratch

- No starter templates or boilerplates
- No agent frameworks (LangChain, LangGraph, etc.)
- No UI component libraries (shadcn, MUI, etc.)
- Dashboard built with plain Tailwind utilities
- All components original, written for this project

## Technical Stack

- **Backend**: Python + FastAPI
- **Database**: PostgreSQL
- **LLM**: Claude API (direct calls, no frameworks)
- **Payments**: Razorpay test mode
- **Frontend**: Next.js 15 + TypeScript + Tailwind
- **Charts**: Recharts (rendering only)

## License

Built for Razorpay Buildathon 2024.

In a separate terminal:

```bash
ngrok http 8000
```

Copy the HTTPS URL and configure it in your Razorpay dashboard:
- Webhook URL: `https://your-ngrok-url.ngrok.io/webhooks/razorpay`
- Events: `payment.failed`, `subscription.charged.failed`, `subscription.pending`

### 8. Test the Webhook

The webhook endpoint verifies `X-Razorpay-Signature` on every request.

Test endpoints:
- `GET /` - Service info
- `GET /health` - Health check
- `POST /webhooks/razorpay` - Webhook receiver (requires valid signature)

## Part 1 Checklist

- [x] Postgres schema created for all 4 tables
- [x] Seed script runs and produces 150-300 realistic records with hard cases and one broken record
- [ ] Razorpay test account connected, keys in `.env` (gitignored)
- [ ] Webhook endpoint live and receiving at least one real test-mode event
- [ ] Webhook signature verification working

## Next Steps

Complete the Razorpay integration:
1. Create a test account at https://dashboard.razorpay.com/signup
2. Get your test API keys from Settings > API Keys
3. Configure webhook URL in Settings > Webhooks
4. Generate a webhook secret
5. Test by triggering a failed payment in test mode

Once webhooks are receiving events, proceed to Part 2.
