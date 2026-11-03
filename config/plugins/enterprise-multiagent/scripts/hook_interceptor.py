#!/usr/bin/env python3
"""
PreToolUse Hook Interceptor for Antigravity Multi-Agent Harness
Operational Mode: AUDIT (Non-blocking observation and compliance logging)

Receives protojson hook payload on stdin:
- toolCall, stepIdx, conversationId, workspacePaths, etc.

Evaluates against session-bound ExecutionPolicy:
- Records POLICY_ID, PLANNED_STRATEGY, EXECUTED_STRATEGY, ACTUAL_WORKERS, CONCURRENCY_PEAK, POLICY_COMPLIANCE.
- Emits structured audit entry in logs/execution_policy_audit.log.
- ALWAYS returns {"decision": "allow"} in AUDIT mode.
- Fails open gracefully if any error occurs.
"""
import sys
import os
import json
import datetime
from typing import Dict, Any

def get_base_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def emit_fallback_allow(reason: str = "Audit mode: tool execution allowed."):
    """Fail-open fallback: always outputs valid allow JSON to stdout."""
    res = {
        "decision": "allow",
        "reason": f"Execution Policy (AUDIT): {reason}"
    }
    sys.stdout.write(json.dumps(res) + "\n")
    sys.stdout.flush()

def main():
    try:
        # Read raw stdin payload
        raw_input = sys.stdin.read().strip()
        if not raw_input:
            emit_fallback_allow("Empty hook input payload")
            return

        try:
            payload = json.loads(raw_input)
        except Exception as e:
            emit_fallback_allow(f"JSON parse error on hook input: {e}")
            return

        conv_id = payload.get("conversationId", "UNKNOWN")
        step_idx = payload.get("stepIdx", 0)
        tool_call = payload.get("toolCall", {})
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})

        base_dir = get_base_dir()
        sessions_dir = os.path.join(base_dir, "sessions")
        logs_dir = os.path.join(base_dir, "logs")
        os.makedirs(sessions_dir, exist_ok=True)
        os.makedirs(logs_dir, exist_ok=True)

        audit_log_path = os.path.join(logs_dir, "execution_policy_audit.log")
        session_file = os.path.join(sessions_dir, f"{conv_id}.json")

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Query session registry for bound policy
        policy_bound = False
        session_data: Dict[str, Any] = {}
        if os.path.isfile(session_file):
            try:
                with open(session_file, "r", encoding="utf-8") as sf:
                    session_data = json.load(sf)
                policy_bound = True
            except Exception:
                policy_bound = False
        else:
            # Fallback: check workspacePaths for EXECUTION_POLICY.json
            for ws in payload.get("workspacePaths", []):
                ws_policy = os.path.join(ws, "EXECUTION_POLICY.json")
                if os.path.isfile(ws_policy):
                    try:
                        with open(ws_policy, "r", encoding="utf-8") as wsf:
                            session_data = json.load(wsf)
                        policy_bound = True
                        session_data["CONVERSATION_ID"] = conv_id
                        with open(session_file, "w", encoding="utf-8") as sf:
                            json.dump(session_data, sf, indent=2)
                        break
                    except Exception:
                        pass

        if policy_bound:
            policy_id = session_data.get("POLICY_ID", "UNKNOWN")
            planned_strategy = session_data.get("PLANNED_STRATEGY", "UNKNOWN")
            required_workers = session_data.get("REQUIRED_WORKERS", 0)
            actual_workers = session_data.get("ACTUAL_WORKERS", 0) + 1
            session_data["ACTUAL_WORKERS"] = actual_workers
            session_data["LAST_UPDATED"] = now_utc

            # Track subagent worker details
            workers_list = session_data.get("DISPATCHED_WORKERS", [])
            role = tool_args.get("Role", "Unknown") if isinstance(tool_args, dict) else "Unknown"
            type_name = tool_args.get("TypeName", "Unknown") if isinstance(tool_args, dict) else "Unknown"
            workers_list.append({
                "step_idx": step_idx,
                "role": role,
                "type_name": type_name,
                "timestamp": now_utc
            })
            session_data["DISPATCHED_WORKERS"] = workers_list

            # Peak concurrency heuristic during active dispatch wave
            concurrency_peak = min(4, actual_workers)
            session_data["CONCURRENCY_PEAK"] = concurrency_peak

            # Evaluate compliance
            if planned_strategy == "INLINE":
                executed_strategy = "PARALLEL" if actual_workers > 1 else "BATCH"
                policy_compliance = "DEVIATION"
                detail_msg = f"Violation: Policy planned INLINE (0 workers), but invoke_subagent was dispatched (worker #{actual_workers}: {role})."
            elif planned_strategy == "BATCH":
                if actual_workers == 1:
                    executed_strategy = "BATCH"
                    policy_compliance = "PASS"
                    detail_msg = f"Compliant: Exactly 1 dedicated worker dispatched ({role})."
                else:
                    executed_strategy = "PARALLEL"
                    policy_compliance = "DEVIATION"
                    detail_msg = f"Violation: Policy planned BATCH (max 1 worker), but multiple workers dispatched (worker #{actual_workers}: {role})."
            elif planned_strategy == "PARALLEL":
                executed_strategy = "PARALLEL"
                policy_compliance = "PASS"
                detail_msg = f"Compliant: Worker #{actual_workers} ({role}) dispatched under PARALLEL strategy."
            else:
                executed_strategy = "UNKNOWN"
                policy_compliance = "UNKNOWN"
                detail_msg = f"Unknown planned strategy: {planned_strategy}"

            # Save updated session data
            try:
                with open(session_file, "w", encoding="utf-8") as sf:
                    json.dump(session_data, sf, indent=2)
            except Exception:
                pass

        else:
            # No policy bound to this session -> Fail-open without blocking
            policy_id = "UNBOUND"
            planned_strategy = "UNKNOWN"
            executed_strategy = "UNKNOWN"
            required_workers = 0
            actual_workers = 1
            concurrency_peak = 1
            policy_compliance = "UNKNOWN"
            detail_msg = f"No execution policy registered for session {conv_id}. Tool call allowed (fail-open)."

        # Record audit entry in JSONL format
        audit_entry = {
            "TIMESTAMP": now_utc,
            "CONVERSATION_ID": conv_id,
            "STEP_IDX": step_idx,
            "TOOL_NAME": tool_name,
            "POLICY_ID": policy_id,
            "PLANNED_STRATEGY": planned_strategy,
            "EXECUTED_STRATEGY": executed_strategy,
            "REQUIRED_WORKERS": required_workers,
            "ACTUAL_WORKERS": actual_workers,
            "CONCURRENCY_PEAK": concurrency_peak,
            "POLICY_COMPLIANCE": policy_compliance,
            "ACTION_TAKEN": "ALLOW",
            "OPERATIONAL_MODE": "AUDIT",
            "DETAILS": detail_msg
        }

        try:
            with open(audit_log_path, "a", encoding="utf-8") as alf:
                alf.write(json.dumps(audit_entry) + "\n")
        except Exception:
            pass

        # Return ALLOW to Antigravity runtime (AUDIT MODE: NEVER BLOCKS)
        emit_fallback_allow(detail_msg)

    except Exception as e:
        # Top-level global exception safety net
        emit_fallback_allow(f"Safe fallback on exception: {e}")

if __name__ == "__main__":
    main()
