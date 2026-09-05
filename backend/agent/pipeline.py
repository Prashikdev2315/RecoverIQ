import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
from database import execute_query
from agent import detector, diagnoser, decision_engine, action_executor
from agent.logging_config import get_logger, set_correlation_id, generate_correlation_id
from agent.notification_service import send_notification

logger = get_logger(__name__)

def reconcile_payment_state(record: Dict[str, Any], record_type: str) -> Dict[str, bool]:
    """
    Reconciliation check before acting.

    Prevents acting on stale state - confirms the record is still genuinely failed/pending,
    not success/refunded as of right now.

    Args:
        record: The event record
        record_type: Record type (transaction/checkout_session/subscription)

    Returns:
        {
            'should_process': bool,
            'reason': str,
            'current_state': str
        }
    """

    record_id = record.get('id')

    if not record_id:
        return {
            'should_process': True,
            'reason': 'No record ID to reconcile',
            'current_state': 'unknown'
        }

    # Re-read current status from database
    if record_type == 'transaction':
        query = "SELECT status FROM transactions WHERE id = %s"
    elif record_type == 'checkout_session':
        query = "SELECT stage_reached FROM checkout_sessions WHERE id = %s"
    elif record_type == 'subscription':
        query = "SELECT status FROM subscriptions WHERE id = %s"
    else:
        return {
            'should_process': True,
            'reason': 'Unknown record type',
            'current_state': 'unknown'
        }

    try:
        result = execute_query(query, (record_id,), fetch=True)

        if not result:
            return {
                'should_process': False,
                'reason': 'Reconciliation check: record no longer exists',
                'current_state': 'deleted'
            }

        current_record = result[0]

        # Check if status has changed to terminal/success state
        if record_type == 'transaction':
            current_status = current_record.get('status')
            if current_status in ['success', 'refunded']:
                return {
                    'should_process': False,
                    'reason': f'Reconciliation check: status changed to {current_status} since trigger, action aborted',
                    'current_state': current_status
                }
            return {
                'should_process': True,
                'reason': 'Status still failed/pending',
                'current_state': current_status
            }

        elif record_type == 'checkout_session':
            stage = current_record.get('stage_reached')
            if stage == 'completed':
                return {
                    'should_process': False,
                    'reason': 'Reconciliation check: checkout completed since trigger, action aborted',
                    'current_state': 'completed'
                }
            return {
                'should_process': True,
                'reason': 'Checkout still abandoned',
                'current_state': stage
            }

        elif record_type == 'subscription':
            current_status = current_record.get('status')
            if current_status == 'active':
                return {
                    'should_process': False,
                    'reason': 'Reconciliation check: subscription activated since trigger, action aborted',
                    'current_state': 'active'
                }
            return {
                'should_process': True,
                'reason': 'Subscription still failed',
                'current_state': current_status
            }

    except Exception as e:
        print(f"✗ Reconciliation check failed: {e}")
        # FAIL CLOSED - abort action to prevent double-charging during DB issues
        return {
            'should_process': False,
            'reason': f'Reconciliation check failed - aborting for safety: {str(e)}',
            'current_state': 'error'
        }

def process_event(record: Dict[str, Any], record_type: str) -> Dict[str, Any]:
    """
    Main pipeline orchestrator.
    Runs: Detector → Diagnoser → Decision Engine → Action Executor

    Args:
        record: The event record (transaction/checkout_session/subscription)
        record_type: One of 'transaction', 'checkout_session', 'subscription'

    Returns:
        {
            'success': bool,
            'recovery_action_id': str (if created),
            'status': str,
            'error': str (if failed)
        }
    """

    print(f"\n{'='*60}")
    print(f"Processing {record_type}: {record.get('id')}")
    print(f"{'='*60}")

    # Track real pipeline processing time (wall-clock seconds)
    pipeline_start = time.perf_counter()
    pipeline_start_dt = datetime.now()

    try:
        # Step 0: Reconciliation check - verify state hasn't changed
        print("→ Step 0: Reconciliation check")
        reconciliation_result = reconcile_payment_state(record, record_type)

        if not reconciliation_result['should_process']:
            print(f"  ✓ Aborting: {reconciliation_result['reason']}")
            return {
                'success': True,
                'recovery_action_id': None,
                'status': 'no_action',
                'reason': reconciliation_result['reason']
            }

        print(f"  ✓ State confirmed: {reconciliation_result['current_state']}")

        # Step 1: Detect - classify event type and severity
        print("→ Step 1: Detection")
        classification = detector.detect(record, record_type)

        if not classification.get('should_process'):
            print(f"  ✓ Skipping: {classification.get('reason')}")
            return {
                'success': True,
                'recovery_action_id': None,
                'status': 'skipped',
                'reason': classification.get('reason')
            }

        print(f"  ✓ Classified as: {classification['event_type'].value}, severity: {classification['severity'].value}")

        # Step 2: Diagnose - determine root cause
        print("→ Step 2: Diagnosis")

        # Fetch transaction history for context (if transaction)
        transaction_history = None
        if record_type == 'transaction':
            transaction_history = get_transaction_history(record.get('customer_id'))

        diagnosis = diagnoser.diagnose(record, classification, transaction_history)
        print(f"  ✓ Diagnosis: {diagnosis['diagnosis']} (method: {diagnosis['method']})")
        print(f"    Root cause: {diagnosis['root_cause']}")

        # Step 3: Decide - map diagnosis to action
        print("→ Step 3: Decision")
        decision = decision_engine.decide(diagnosis, classification)
        print(f"  ✓ Proposed action: {decision['action']} (confidence: {decision['confidence']:.2f})")
        print(f"    Reason: {decision['reason']}")

        # Step 4: Execute with guardrails
        print("→ Step 4: Execution")
        execution_result = action_executor.execute_action(
            decision,
            diagnosis,
            classification,
            record,
            record_type
        )

        print(f"  ✓ Status: {execution_result['status']}")
        if execution_result['status'] == 'blocked_by_guardrail':
            print(f"    Guardrail: {execution_result['guardrail_reason']}")
            print(f"    Fallback action: {execution_result['executed_action']}")

        # Capture real processing duration BEFORE logging
        pipeline_duration_seconds = round(time.perf_counter() - pipeline_start, 4)
        print(f"  Pipeline duration: {pipeline_duration_seconds}s")

        # Step 5: Log to recovery_actions table
        print("→ Step 5: Audit logging")
        recovery_action_id = log_recovery_action(
            record,
            record_type,
            classification,
            diagnosis,
            decision,
            execution_result,
            processed_at=pipeline_start_dt,
            processing_duration_seconds=pipeline_duration_seconds
        )

        print(f"  ✓ Logged to recovery_actions: {recovery_action_id}")
        print(f"\n{'='*60}")
        print(f"✓ Pipeline complete for {record_type}: {record.get('id')}")
        print(f"  Action: {execution_result['executed_action']} ({execution_result['status']})")
        print(f"{'='*60}\n")

        return {
            'success': True,
            'recovery_action_id': recovery_action_id,
            'status': execution_result['status'],
            'action': execution_result['executed_action']
        }

    except Exception as e:
        print(f"\n✗ Pipeline error for {record_type} {record.get('id')}: {e}")
        print(f"{'='*60}\n")

        # Log the error
        try:
            error_action_id = log_error(record, record_type, str(e))
            return {
                'success': False,
                'recovery_action_id': error_action_id,
                'status': 'error',
                'error': str(e)
            }
        except Exception as log_error_ex:
            print(f"✗ Failed to log error: {log_error_ex}")
            return {
                'success': False,
                'recovery_action_id': None,
                'status': 'error',
                'error': str(e)
            }

def get_transaction_history(customer_id: str, limit: int = 10) -> Optional[list]:
    """Fetch recent transaction history for a customer."""

    if not customer_id:
        return None

    query = """
        SELECT id, amount, status, failure_reason, payment_method, created_at, retry_count
        FROM transactions
        WHERE customer_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """

    try:
        results = execute_query(query, (customer_id, limit), fetch=True)
        return results if results else None
    except Exception as e:
        print(f"⚠ Failed to fetch transaction history: {e}")
        return None

def log_recovery_action(
    record: Dict[str, Any],
    record_type: str,
    classification: Dict[str, Any],
    diagnosis: Dict[str, Any],
    decision: Dict[str, Any],
    execution_result: Dict[str, Any],
    processed_at: Optional[datetime] = None,
    processing_duration_seconds: Optional[float] = None
) -> str:
    """
    Log the full decision trail to recovery_actions table.

    Returns:
        recovery_action_id (str)
    """

    # Build comprehensive reasoning log
    reasoning_log = {
        'classification': {
            'event_type': classification['event_type'].value,
            'severity': classification['severity'].value if classification.get('severity') else None,
            'reason': classification.get('reason'),
            'metadata': {k: v for k, v in classification.items() if k not in ['event_type', 'severity', 'should_process', 'reason']}
        },
        'diagnosis': {
            'diagnosis': diagnosis['diagnosis'],
            'root_cause': diagnosis['root_cause'],
            'is_recoverable': diagnosis['is_recoverable'],
            'method': diagnosis['method'],
            'recommended_action_hint': diagnosis.get('recommended_action_hint'),
            'confidence_modifier': diagnosis.get('confidence_modifier'),
            'llm_log': diagnosis.get('llm_log')
        },
        'decision': {
            'proposed_action': decision['action'],
            'confidence': decision['confidence'],
            'reason': decision['reason'],
            'channel': decision['channel'],
            'language': decision['language']
        },
        'execution': {
            'status': execution_result['status'],
            'executed_action': execution_result['executed_action'],
            'guardrail_reason': execution_result.get('guardrail_reason'),
            'execution_log': execution_result['execution_log']
        },
        'timestamp': datetime.now().isoformat()
    }

    # Generate and embed Hinglish message if applicable
    channel = decision.get('channel', 'sms')
    language = decision.get('language', 'en')
    action = execution_result['executed_action']

    # Use real customer_name from record; fall back gracefully if missing
    customer_name = (
        record.get('customer_name')
        or record.get('name')
        or 'Customer'
    )

    if language == 'hinglish' and action in ['send_reminder_sms', 'send_payment_link', 'retry_charge', 'offer_alternate_method']:
        try:
            from agent.message_generator import generate_message_for_action
            message_result = generate_message_for_action(
                action=action,
                record=record,
                diagnosis=diagnosis,
                customer_name=customer_name
            )
            if message_result.get('passes_compliance'):
                reasoning_log['message_generation'] = {
                    'hinglish_message': message_result.get('hinglish_message'),
                    'english_message': message_result.get('english_message'),
                    'character_count': message_result.get('character_count', 0),
                    'compliance_status': message_result.get('compliance_reason'),
                    'generation_method': message_result.get('generation_method', 'template'),
                    'timestamp': datetime.now().isoformat()
                }
        except Exception as msg_e:
            print(f"\u26a0 Message generation failed (non-critical): {msg_e}")

    # Determine final status
    if execution_result['status'] == 'executed':
        status = 'executed'
    elif execution_result['status'] == 'blocked_by_guardrail':
        status = 'blocked_by_guardrail'
    else:
        status = 'proposed'

    query = """
        INSERT INTO recovery_actions
        (target_type, target_id, detected_issue, proposed_action, executed_action,
         confidence_score, channel, language, status, reasoning_log, created_at,
         processed_at, processing_duration_seconds)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    params = (
        record_type,
        record['id'],
        diagnosis['diagnosis'],
        decision['action'],
        execution_result['executed_action'],
        decision['confidence'],
        decision['channel'],
        decision['language'],
        status,
        json.dumps(reasoning_log),
        datetime.now(),
        processed_at or datetime.now(),
        processing_duration_seconds
    )

    result = execute_query(query, params, fetch=True)

    return str(result[0]['id'])

def log_error(record: Dict[str, Any], record_type: str, error_message: str) -> str:
    """Log pipeline error to recovery_actions."""

    reasoning_log = {
        'error': error_message,
        'timestamp': datetime.now().isoformat(),
        'record_snapshot': {k: str(v) for k, v in record.items()}
    }

    query = """
        INSERT INTO recovery_actions
        (target_type, target_id, detected_issue, proposed_action, executed_action,
         confidence_score, channel, language, status, reasoning_log, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    params = (
        record_type,
        record.get('id'),
        'pipeline_error',
        'no_action',
        'no_action',
        0.0,
        'none',
        'en',
        'error',
        json.dumps(reasoning_log),
        datetime.now()
    )

    result = execute_query(query, params, fetch=True)

    return str(result[0]['id'])
