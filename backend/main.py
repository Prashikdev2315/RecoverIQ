import os
import hmac
import hashlib
import json
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from database import get_connection
from agent.pipeline import process_event
from api.metrics import router as metrics_router

load_dotenv()

app = FastAPI(title="AI Revenue Recovery Agent")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register metrics API routes
app.include_router(metrics_router)

RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

def process_payment_failed(event_data: dict):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        payment = event_data.get('payload', {}).get('payment', {}).get('entity', {})

        transaction_data = {
            'razorpay_payment_id': payment.get('id'),
            'amount': payment.get('amount'),
            'status': 'failed',
            'failure_reason': payment.get('error_description', 'unknown'),
            'payment_method': payment.get('method'),
            'created_at': datetime.fromtimestamp(payment.get('created_at', datetime.now().timestamp()))
        }

        cursor.execute(
            """
            INSERT INTO transactions
            (merchant_id, customer_id, amount, status, failure_reason, payment_method, created_at, retry_count)
            VALUES (
                gen_random_uuid(),
                gen_random_uuid(),
                %s, %s, %s, %s, %s, 0
            )
            RETURNING id, merchant_id, customer_id, amount, status, failure_reason, payment_method, created_at, retry_count
            """,
            (
                transaction_data['amount'],
                transaction_data['status'],
                transaction_data['failure_reason'],
                transaction_data['payment_method'],
                transaction_data['created_at']
            )
        )

        transaction_record = cursor.fetchone()
        conn.commit()

        print(f"✓ Processed payment.failed event: {transaction_data['razorpay_payment_id']}")

        # Run recovery pipeline on the new transaction
        if transaction_record:
            print(f"  → Triggering recovery pipeline")
            process_event(dict(transaction_record), 'transaction')

    except Exception as e:
        conn.rollback()
        print(f"✗ Error processing payment.failed: {e}")
        raise
    finally:
        conn.close()

def process_subscription_charged_failed(event_data: dict):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        subscription = event_data.get('payload', {}).get('subscription', {}).get('entity', {})

        cursor.execute(
            """
            INSERT INTO subscriptions
            (customer_id, plan_amount, status, mandate_status, last_charge_attempt, consecutive_failures)
            VALUES (
                gen_random_uuid(),
                %s, 'failed_charge', 'active', %s, 1
            )
            RETURNING id, customer_id, plan_amount, status, mandate_status, last_charge_attempt, consecutive_failures
            """,
            (
                subscription.get('plan_id'),
                datetime.now()
            )
        )

        subscription_record = cursor.fetchone()
        conn.commit()

        print(f"✓ Processed subscription.charged.failed event")

        # Run recovery pipeline on the new subscription
        if subscription_record:
            print(f"  → Triggering recovery pipeline")
            process_event(dict(subscription_record), 'subscription')

    except Exception as e:
        conn.rollback()
        print(f"✗ Error processing subscription.charged.failed: {e}")
        raise
    finally:
        conn.close()

@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    """
    Handle Razorpay webhook events.
    Supports:
    - payment.captured: Mark recovery as successful
    - subscription.charged: Mark subscription recovery as successful
    - payment.failed: Trigger recovery pipeline
    """
    from agent.webhook_handler import verify_razorpay_signature, process_webhook_event

    signature = request.headers.get('X-Razorpay-Signature')

    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature header")

    body = await request.body()

    if not verify_razorpay_signature(body, signature, RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event_data = json.loads(body)
        event_type = event_data.get('event')
        event_id = event_data.get('event_id')

        print(f"📥 Webhook received: {event_type} (event_id: {event_id})")

        # Process the event
        result = process_webhook_event(event_data)

        return {
            "status": "success",
            "event": event_type,
            "event_id": event_id,
            "processing_result": result
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        print(f"✗ Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
async def health_check():
    """
    Comprehensive health check: verifies DB connection and LLM reachability.
    Returns 200 if healthy, 503 if any component is down.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }

    # Check database connection
    try:
        from database import execute_query
        result = execute_query("SELECT 1 as health_check", fetch=True)
        if result and result[0]['health_check'] == 1:
            health_status["components"]["database"] = {
                "status": "healthy",
                "message": "Connection pool operational"
            }
        else:
            health_status["components"]["database"] = {
                "status": "degraded",
                "message": "Query returned unexpected result"
            }
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "message": f"Connection failed: {str(e)}"
        }
        health_status["status"] = "unhealthy"

    # Check LLM circuit breaker state
    try:
        from agent.llm_client import _consecutive_failures, _circuit_open_until
        if _circuit_open_until and datetime.now() < _circuit_open_until:
            health_status["components"]["llm"] = {
                "status": "degraded",
                "message": f"Circuit breaker open, {_consecutive_failures} consecutive failures",
                "cooldown_until": _circuit_open_until.isoformat()
            }
            health_status["status"] = "degraded"
        elif _consecutive_failures > 0:
            health_status["components"]["llm"] = {
                "status": "degraded",
                "message": f"{_consecutive_failures} recent failures, circuit still closed"
            }
            health_status["status"] = "degraded"
        else:
            health_status["components"]["llm"] = {
                "status": "healthy",
                "message": "No recent failures"
            }
    except Exception as e:
        health_status["components"]["llm"] = {
            "status": "unknown",
            "message": f"Could not check circuit breaker: {str(e)}"
        }

    # Return 503 if any component is unhealthy
    status_code = 200 if health_status["status"] in ["healthy", "degraded"] else 503

    return Response(
        content=json.dumps(health_status),
        media_type="application/json",
        status_code=status_code
    )

@app.get("/")
async def root():
    return {
        "service": "AI Revenue Recovery Agent",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/webhooks/razorpay",
            "health": "/health"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
