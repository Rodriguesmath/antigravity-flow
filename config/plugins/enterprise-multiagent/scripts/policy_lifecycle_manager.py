"""
Policy Lifecycle Manager for Antigravity Multi-Agent Harness
Operational Mode: AUDIT (Non-blocking observation, deterministic policy binding and transcript verification)

Provides:
- Automated ExecutionPolicy generation via Task Sizing Gate heuristics (no arbitrary forced scores).
- Concurrency-safe session and task policy binding (POSIX flock + atomic replace).
- Lifecycle Hook Handlers (SessionStart, PreToolUse, Stop).
- Provisional Compliance tracking during dispatch (PROVISIONAL_PASS vs PROVISIONAL_DEVIATION vs PENDING).
- Full post-execution transcript audit with temporal overlap & peak concurrency computation.
- Comprehensive deviation classification:
    * INLINE_WITH_SUBAGENTS
    * BATCH_ZERO_WORKERS
    * BATCH_MULTIPLE_WORKERS
    * PARALLEL_INSUFFICIENT_WORKERS
    * PARALLEL_SERIALIZED_NO_OVERLAP
    * TOOL_DISALLOWED
- Historical archival and fail-open guarantees.
"""
import os
import sys
import json
import re
import time
import fcntl
import datetime
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple

from task_sizing_gate import (
    AdaptiveTaskSizingGate,
    TaskCharacteristics,
    SizingDecision,
    SizingStrategy,
    ConfidenceLevel,
    load_feature_flags
)
from execution_policy import (
    ExecutionPolicy,
    PolicyFactory,
    EnforcementMode,
    ComplianceStatus
)


class ProvisionalComplianceStatus(str, Enum):
    PROVISIONAL_PASS = "PROVISIONAL_PASS"
    PROVISIONAL_DEVIATION = "PROVISIONAL_DEVIATION"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


class FinalComplianceStatus(str, Enum):
    PASS = "PASS"
    DEVIATION = "DEVIATION"
    UNKNOWN = "UNKNOWN"


class DeviationType(str, Enum):
    NONE = "NONE"
    INLINE_WITH_SUBAGENTS = "INLINE_WITH_SUBAGENTS"
    BATCH_ZERO_WORKERS = "BATCH_ZERO_WORKERS"
    BATCH_MULTIPLE_WORKERS = "BATCH_MULTIPLE_WORKERS"
    PARALLEL_INSUFFICIENT_WORKERS = "PARALLEL_INSUFFICIENT_WORKERS"
    PARALLEL_SERIALIZED_NO_OVERLAP = "PARALLEL_SERIALIZED_NO_OVERLAP"
    TOOL_DISALLOWED = "TOOL_DISALLOWED"
    UNKNOWN = "UNKNOWN"


@dataclass
class TaskAnalysisResult:
    task_id: str
    module_count: int
    complexity_score: int
    dependency_ratio: float
    estimated_work_sec_per_module: float
    confidence_variance: float
    security_risk: bool
    rationale: str
    extracted_entities: List[str] = field(default_factory=list)


@dataclass
class AuditFinalResult:
    policy_id: str
    conversation_id: str
    task_id: str
    planned_strategy: SizingStrategy
    executed_strategy: SizingStrategy
    required_workers: int
    actual_workers: int
    concurrency_peak: int
    temporal_overlap_sec: float
    provisional_compliance: ProvisionalComplianceStatus
    final_compliance: FinalComplianceStatus
    deviation_type: DeviationType
    deviation_details: Optional[str]
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    verified_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "POLICY_ID": self.policy_id,
            "CONVERSATION_ID": self.conversation_id,
            "TASK_ID": self.task_id,
            "PLANNED_STRATEGY": self.planned_strategy.value,
            "EXECUTED_STRATEGY": self.executed_strategy.value,
            "REQUIRED_WORKERS": self.required_workers,
            "ACTUAL_WORKERS": self.actual_workers,
            "CONCURRENCY_PEAK": self.concurrency_peak,
            "TEMPORAL_OVERLAP_SEC": round(self.temporal_overlap_sec, 2),
            "PROVISIONAL_COMPLIANCE": self.provisional_compliance.value,
            "FINAL_COMPLIANCE": self.final_compliance.value,
            "DEVIATION_TYPE": self.deviation_type.value,
            "DEVIATION_DETAILS": self.deviation_details,
            "TIMELINE": self.timeline,
            "VERIFIED_AT": self.verified_at
        }


class AutomatedTaskAnalyzer:
    """
    Analyzes task input and workspace environment to infer TaskCharacteristics
    deterministically without relying on arbitrary hardcoded complexity scores.
    """

    FILE_PATH_REGEX = re.compile(
        r'(?:[\w.-]+/)*[\w.-]+\.(?:py|ts|js|jsx|tsx|json|yaml|yml|toml|go|rs|cpp|c|h|java|sh|md)',
        re.IGNORECASE
    )

    TRIVIAL_KEYWORDS = [
        "typo", "fix comment", "rename", "one-line", "docstring", "trivial",
        "pequena alteração", "read-only", "ajuste simples", "hello world", "print"
    ]

    COMPLEX_KEYWORDS = [
        "refactor", "arquitetura", "architecture", "multi-module", "distributed",
        "concurrency", "paralelo", "concorrente", "thread", "asyncio", "lock",
        "worktree", "migration", "pipeline", "benchmark", "multiagent"
    ]

    CRITICAL_KEYWORDS = [
        "critical safety", "zero-trust", "cryptography", "compiler", "kernel",
        "consensus", "clinical safety", "sandbox boundary", "privilege"
    ]

    SECURITY_KEYWORDS = [
        "secret", "auth", "credential", "crypto", "sql", "firewall",
        "permission", "sandbox", "token", "password", "jwt"
    ]

    PIPELINE_KEYWORDS = [
        "primeiro", "depois", "em seguida", "após", "depende", "sequencial",
        "pipeline", "cascade", "prerequisite", "waterfall", "strict order", "first", "then", "after"
    ]

    INDEPENDENT_KEYWORDS = [
        "independente", "disjunto", "paralelo", "isolado", "sem dependência",
        "concurrent", "disjoint", "independent", "decoupled"
    ]

    @classmethod
    def analyze(
        cls,
        task_input: str,
        workspace_paths: Optional[List[str]] = None,
        task_id: Optional[str] = None
    ) -> TaskCharacteristics:
        text = task_input or ""
        text_lower = text.lower()

        # 1. Deterministic Task ID
        if not task_id:
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
            task_id = f"task-{h}"

        # 2. Module Count Extraction
        extracted_files = list(set(cls.FILE_PATH_REGEX.findall(text)))
        module_count = max(1, len(extracted_files))

        # Check for multiple target indicators in text if no files matched
        if module_count == 1:
            multi_indicators = len(re.findall(r'(?:módulo|module|componente|component|subtarefa|worker)\s+[a-z0-9_]+', text_lower))
            if multi_indicators > 1:
                module_count = min(multi_indicators, 4)

        # 3. Complexity Score Inference (1..5)
        is_trivial = any(k in text_lower for k in cls.TRIVIAL_KEYWORDS)
        is_critical = any(k in text_lower for k in cls.CRITICAL_KEYWORDS)
        complex_matches = sum(1 for k in cls.COMPLEX_KEYWORDS if k in text_lower)

        # Count requirement bullet points
        bullet_points = len(re.findall(r'^\s*[-*0-9]+[.)]\s+', text, re.MULTILINE))

        if is_trivial and len(text) < 300 and module_count == 1:
            score = 1
        elif is_critical:
            score = 5
        elif complex_matches >= 2 or bullet_points >= 6 or module_count >= 3:
            score = 4
        elif complex_matches >= 1 or bullet_points >= 3 or module_count >= 2:
            score = 3
        else:
            score = 2

        # 4. Dependency Ratio Inference (0.0..1.0)
        has_pipeline = any(k in text_lower for k in cls.PIPELINE_KEYWORDS)
        has_independent = any(k in text_lower for k in cls.INDEPENDENT_KEYWORDS)

        if has_pipeline and not has_independent:
            dep_ratio = 0.85
        elif has_independent and not has_pipeline:
            dep_ratio = 0.10
        elif module_count > 1:
            dep_ratio = 0.35
        else:
            dep_ratio = 0.0

        # 5. Work sec estimation (empirical scaling from complexity)
        work_sec_map = {1: 15.0, 2: 35.0, 3: 65.0, 4: 120.0, 5: 180.0}
        estimated_work_sec = work_sec_map.get(score, 35.0)

        # 6. Confidence Variance
        # Short or vague descriptions get higher CV (0.30), driving conservative fallback
        if len(text.strip()) < 50 or (module_count == 1 and score == 2 and not extracted_files):
            cv = 0.30
        else:
            cv = 0.15

        # 7. Security Risk
        security_risk = any(k in text_lower for k in cls.SECURITY_KEYWORDS)

        return TaskCharacteristics(
            task_id=task_id,
            module_count=module_count,
            complexity_score=score,
            dependency_ratio=dep_ratio,
            estimated_work_sec_per_module=estimated_work_sec,
            has_historical_data=True,
            historical_cv=cv,
            security_risk=security_risk
        )


class SessionLock:
    """POSIX file lock wrapper to serialize concurrent hook updates and prevent races."""

    def __init__(self, lock_dir: str, conv_id: str, timeout_sec: float = 5.0):
        self.lock_dir = lock_dir
        self.conv_id = conv_id
        self.timeout_sec = timeout_sec
        self.lock_file_path = os.path.join(lock_dir, f"{conv_id}.lock")
        self.fd = None

    def __enter__(self):
        os.makedirs(self.lock_dir, exist_ok=True)
        try:
            self.fd = os.open(self.lock_file_path, os.O_CREAT | os.O_RDWR, 0o666)
            start_time = time.time()
            while True:
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, IOError):
                    if time.time() - start_time > self.timeout_sec:
                        # Fail-open: proceed without hard block if lock timed out
                        break
                    time.sleep(0.05)
        except Exception:
            self.fd = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
            except Exception:
                pass


class PolicyLifecycleManager:
    """
    Manages end-to-end lifecycle of Execution Policies:
    - Automated task analysis & sizing gate evaluation
    - Safe session storage with atomic replacement & locking
    - Provisional tool dispatch interception
    - Full post-session transcript verification & deviation detection
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        brain_root: Optional[str] = None,
        sizing_gate: Optional[AdaptiveTaskSizingGate] = None
    ):
        if base_dir:
            self.base_dir = base_dir
        else:
            # Default to enterprise-multiagent plugin root
            self.base_dir = os.path.expanduser("~/.gemini/config/plugins/enterprise-multiagent")

        self.brain_root = brain_root or os.path.expanduser("~/.gemini/antigravity-cli/brain")
        self.sessions_dir = os.path.join(self.base_dir, "sessions")
        self.logs_dir = os.path.join(self.base_dir, "logs")
        self.history_dir = os.path.join(self.base_dir, "history")
        self.locks_dir = os.path.join(self.sessions_dir, ".locks")

        os.makedirs(self.sessions_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.history_dir, exist_ok=True)
        os.makedirs(self.locks_dir, exist_ok=True)

        self.sizing_gate = sizing_gate or AdaptiveTaskSizingGate()

    def _get_session_path(self, conversation_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{conversation_id}.json")

    def _atomic_write_json(self, target_path: str, data: Dict[str, Any]) -> None:
        """Writes JSON to temporary file and atomically replaces destination."""
        tmp_path = f"{target_path}.tmp.{uuid.uuid4().hex[:8]}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _append_jsonl_log(self, filename: str, entry: Dict[str, Any]) -> None:
        log_path = os.path.join(self.logs_dir, filename)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def create_and_bind_policy(
        self,
        conversation_id: str,
        task_input: str,
        task_id: Optional[str] = None,
        workspace_paths: Optional[List[str]] = None
    ) -> ExecutionPolicy:
        """
        Infers characteristics from task_input, runs Task Sizing Gate,
        creates deterministic ExecutionPolicy, and binds to conversation session.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        session_path = self._get_session_path(conversation_id)

        with SessionLock(self.locks_dir, conversation_id):
            # Check existing session state to prevent accidental overwrite or duplication
            session_data: Dict[str, Any] = {}
            if os.path.isfile(session_path):
                try:
                    with open(session_path, "r", encoding="utf-8") as f:
                        session_data = json.load(f)
                except Exception:
                    session_data = {}

            # If policy already bound and matches active task, return existing policy
            tasks_map = session_data.get("TASKS", {})
            active_task_id = task_id or session_data.get("ACTIVE_TASK_ID")

            if active_task_id and active_task_id in tasks_map:
                existing_policy_dict = tasks_map[active_task_id].get("POLICY")
                if existing_policy_dict:
                    return ExecutionPolicy(
                        policy_id=existing_policy_dict["POLICY_ID"],
                        task_sizing_decision=SizingStrategy(existing_policy_dict["TASK_SIZING_DECISION"]),
                        required_workers=existing_policy_dict["REQUIRED_WORKERS"],
                        allowed_tools=existing_policy_dict["ALLOWED_TOOLS"],
                        estimated_speedup=existing_policy_dict["ESTIMATED_SPEEDUP"],
                        estimation_confidence=ConfidenceLevel(existing_policy_dict["ESTIMATION_CONFIDENCE"]),
                        fallback_strategy=SizingStrategy(existing_policy_dict["FALLBACK_STRATEGY"]),
                        enforcement_mode=EnforcementMode(existing_policy_dict["ENFORCEMENT_MODE"]),
                        notes=existing_policy_dict.get("NOTES")
                    )

            # Analyze task input objectively
            task_char = AutomatedTaskAnalyzer.analyze(task_input, workspace_paths, task_id)
            effective_task_id = task_char.task_id

            # Evaluate with Task Sizing Gate
            decision = self.sizing_gate.evaluate(task_char)

            # Create deterministic Policy
            policy = PolicyFactory.create_policy(decision, effective_task_id)

            # Store in session state
            task_record = {
                "TASK_ID": effective_task_id,
                "POLICY": policy.to_dict(),
                "TASK_CHARACTERISTICS": {
                    "module_count": task_char.module_count,
                    "complexity_score": task_char.complexity_score,
                    "dependency_ratio": task_char.dependency_ratio,
                    "estimated_work_sec": task_char.estimated_work_sec_per_module,
                    "historical_cv": task_char.historical_cv,
                    "security_risk": task_char.security_risk
                },
                "PROVISIONAL_COMPLIANCE": ProvisionalComplianceStatus.PENDING.value,
                "DISPATCHED_WORKERS": [],
                "ACTUAL_WORKERS": 0,
                "CONCURRENCY_PEAK": 0,
                "CREATED_AT": now_utc,
                "UPDATED_AT": now_utc
            }

            tasks_map[effective_task_id] = task_record
            session_data["CONVERSATION_ID"] = conversation_id
            session_data["ACTIVE_TASK_ID"] = effective_task_id
            session_data["TASKS"] = tasks_map

            # Top-level backward compatibility fields
            session_data.update(policy.to_dict())
            session_data["PLANNED_STRATEGY"] = policy.task_sizing_decision.value
            session_data["ACTUAL_WORKERS"] = 0
            session_data["CONCURRENCY_PEAK"] = 0
            session_data["POLICY_COMPLIANCE"] = ProvisionalComplianceStatus.PENDING.value
            session_data["LAST_UPDATED"] = now_utc

            self._atomic_write_json(session_path, session_data)

            # Record creation in lifecycle log
            lifecycle_entry = {
                "EVENT": "POLICY_BOUND",
                "TIMESTAMP": now_utc,
                "CONVERSATION_ID": conversation_id,
                "TASK_ID": effective_task_id,
                "POLICY_ID": policy.policy_id,
                "PLANNED_STRATEGY": policy.task_sizing_decision.value,
                "REQUIRED_WORKERS": policy.required_workers,
                "ESTIMATED_SPEEDUP": policy.estimated_speedup,
                "CONFIDENCE": policy.estimation_confidence.value
            }
            self._append_jsonl_log("policy_lifecycle.jsonl", lifecycle_entry)

            return policy

    def record_tool_dispatch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        PreToolUse Hook handler.
        Tracks subagent dispatches, evaluates Provisional Compliance, and logs audit events.
        Always returns allow (fail-open) in AUDIT mode.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conv_id = payload.get("conversationId", "UNKNOWN")
        step_idx = payload.get("stepIdx", 0)
        tool_call = payload.get("toolCall", {})
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})

        session_path = self._get_session_path(conv_id)

        with SessionLock(self.locks_dir, conv_id):
            session_data: Dict[str, Any] = {}
            if os.path.isfile(session_path):
                try:
                    with open(session_path, "r", encoding="utf-8") as f:
                        session_data = json.load(f)
                except Exception:
                    session_data = {}

            # Fallback policy discovery if unbound
            if not session_data:
                # Check workspacePaths for pre-existing EXECUTION_POLICY.json
                for ws in payload.get("workspacePaths", []):
                    ws_pol = os.path.join(ws, "EXECUTION_POLICY.json")
                    if os.path.isfile(ws_pol):
                        try:
                            with open(ws_pol, "r", encoding="utf-8") as wsf:
                                session_data = json.load(wsf)
                            session_data["CONVERSATION_ID"] = conv_id
                            break
                        except Exception:
                            pass

            policy_id = session_data.get("POLICY_ID", "UNBOUND")
            planned_strategy = session_data.get("PLANNED_STRATEGY", session_data.get("TASK_SIZING_DECISION", "UNKNOWN"))
            required_workers = session_data.get("REQUIRED_WORKERS", 0)

            active_task_id = session_data.get("ACTIVE_TASK_ID", "default_task")
            tasks_map = session_data.get("TASKS", {})
            task_record = tasks_map.get(active_task_id, {})

            if tool_name == "invoke_subagent":
                actual_workers = session_data.get("ACTUAL_WORKERS", 0) + 1
                session_data["ACTUAL_WORKERS"] = actual_workers

                role = tool_args.get("Role", "Unknown") if isinstance(tool_args, dict) else "Unknown"
                type_name = tool_args.get("TypeName", "Unknown") if isinstance(tool_args, dict) else "Unknown"

                worker_meta = {
                    "step_idx": step_idx,
                    "role": role,
                    "type_name": type_name,
                    "timestamp": now_utc
                }

                workers_list = session_data.get("DISPATCHED_WORKERS", [])
                workers_list.append(worker_meta)
                session_data["DISPATCHED_WORKERS"] = workers_list

                concurrency_peak = min(4, actual_workers)
                session_data["CONCURRENCY_PEAK"] = concurrency_peak

                # Provisional Compliance evaluation
                if planned_strategy == "INLINE":
                    provisional_compliance = ProvisionalComplianceStatus.PROVISIONAL_DEVIATION
                    detail_msg = f"Provisional Violation: Policy planned INLINE (0 workers), but invoke_subagent dispatched (worker #{actual_workers}: {role})."
                elif planned_strategy == "BATCH":
                    if actual_workers == 1:
                        provisional_compliance = ProvisionalComplianceStatus.PROVISIONAL_PASS
                        detail_msg = f"Provisional Compliant: Exactly 1 worker dispatched ({role}) under BATCH strategy."
                    else:
                        provisional_compliance = ProvisionalComplianceStatus.PROVISIONAL_DEVIATION
                        detail_msg = f"Provisional Violation: Policy planned BATCH (1 worker), but multiple workers dispatched (worker #{actual_workers}: {role})."
                elif planned_strategy == "PARALLEL":
                    if actual_workers == 1:
                        provisional_compliance = ProvisionalComplianceStatus.PENDING
                        detail_msg = f"Provisional Pending: Worker #{actual_workers} ({role}) dispatched under PARALLEL strategy. Awaiting subsequent workers."
                    else:
                        provisional_compliance = ProvisionalComplianceStatus.PROVISIONAL_PASS
                        detail_msg = f"Provisional Compliant: Worker #{actual_workers} ({role}) dispatched under PARALLEL wave."
                else:
                    provisional_compliance = ProvisionalComplianceStatus.UNKNOWN
                    detail_msg = f"No policy registered for session {conv_id}."

                session_data["POLICY_COMPLIANCE"] = provisional_compliance.value
                session_data["LAST_UPDATED"] = now_utc

                if task_record:
                    task_record["ACTUAL_WORKERS"] = actual_workers
                    task_record["CONCURRENCY_PEAK"] = concurrency_peak
                    task_record["PROVISIONAL_COMPLIANCE"] = provisional_compliance.value
                    task_record.setdefault("DISPATCHED_WORKERS", []).append(worker_meta)
                    task_record["UPDATED_AT"] = now_utc

                self._atomic_write_json(session_path, session_data)

            else:
                actual_workers = session_data.get("ACTUAL_WORKERS", 0)
                concurrency_peak = session_data.get("CONCURRENCY_PEAK", 0)
                provisional_compliance = ProvisionalComplianceStatus.UNKNOWN
                detail_msg = f"Non-subagent tool call: {tool_name}"

            # Emit audit entry
            audit_entry = {
                "TIMESTAMP": now_utc,
                "CONVERSATION_ID": conv_id,
                "STEP_IDX": step_idx,
                "TOOL_NAME": tool_name,
                "POLICY_ID": policy_id,
                "PLANNED_STRATEGY": planned_strategy,
                "EXECUTED_STRATEGY": "PARALLEL" if actual_workers > 1 else ("BATCH" if actual_workers == 1 else "INLINE"),
                "REQUIRED_WORKERS": required_workers,
                "ACTUAL_WORKERS": actual_workers,
                "CONCURRENCY_PEAK": concurrency_peak,
                "POLICY_COMPLIANCE": provisional_compliance.value,
                "ACTION_TAKEN": "ALLOW",
                "OPERATIONAL_MODE": "AUDIT",
                "DETAILS": detail_msg
            }
            self._append_jsonl_log("execution_policy_audit.log", audit_entry)

        # Return ALLOW in AUDIT mode
        return {
            "decision": "allow",
            "reason": f"Execution Policy (AUDIT): {detail_msg}"
        }

    def _extract_timeline_and_concurrency(
        self,
        transcript_path: str
    ) -> Tuple[List[Dict[str, Any]], int, float]:
        """
        Full transcript parsing to extract subagent lifespans [t_start, t_end],
        calculate exact peak concurrency, and continuous temporal overlap duration.
        """
        if not os.path.isfile(transcript_path):
            return [], 0, 0.0

        subagents_map: Dict[str, Dict[str, Any]] = {}
        last_step_time = None

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        step = json.loads(line)
                    except Exception:
                        continue

                    created_at = step.get("created_at")
                    if created_at:
                        last_step_time = created_at

                    # Check tool calls
                    for tc in step.get("tool_calls", []):
                        if tc.get("name") == "invoke_subagent":
                            s_idx = str(step.get("step_index", len(subagents_map)))
                            args = tc.get("args", {})
                            role_raw = args.get("Role", "Unknown")
                            type_raw = args.get("TypeName", "Unknown")
                            prompt_raw = args.get("Prompt", "")
                            subagents_map[s_idx] = {
                                "step_index": step.get("step_index"),
                                "role": str(role_raw).strip("\"'"),
                                "type_name": str(type_raw).strip("\"'"),
                                "prompt": str(prompt_raw).strip("\"'")[:100],
                                "conv_id": None,
                                "start": created_at,
                                "end": None
                            }

                    # Check content for child conversationId
                    content = str(step.get("content", ""))
                    if "Created the following subagent:" in content or "Created subagent" in content:
                        for s_idx, s_data in subagents_map.items():
                            if s_data["conv_id"] is None and '"conversationId":' in content:
                                try:
                                    cid = content.split('"conversationId":')[1].split('"')[1]
                                    s_data["conv_id"] = cid
                                except Exception:
                                    pass
                                break

                    # Check for subagent completion message
                    if "[Message]" in content and "sender=" in content:
                        for s_idx, s_data in subagents_map.items():
                            if s_data["conv_id"] and f"sender={s_data['conv_id']}" in content and s_data["end"] is None:
                                s_data["end"] = created_at
                                break
        except Exception:
            return [], 0, 0.0

        # Close any unclosed intervals with last_step_time
        for s_data in subagents_map.values():
            if s_data["start"] and s_data["end"] is None:
                s_data["end"] = last_step_time or s_data["start"]

        def parse_iso(ts: Optional[str]) -> float:
            if not ts:
                return 0.0
            try:
                clean_ts = ts.replace("Z", "+00:00")
                return datetime.datetime.fromisoformat(clean_ts).timestamp()
            except Exception:
                return 0.0

        intervals = []
        for s_data in subagents_map.values():
            st = parse_iso(s_data.get("start"))
            et = parse_iso(s_data.get("end"))
            if st and et and et >= st:
                intervals.append((st, et))

        timeline = list(subagents_map.values())
        if not intervals:
            return timeline, (1 if timeline else 0), 0.0

        # Calculate exact temporal overlap & peak concurrency via event sweep
        events = sorted(set([t for st, et in intervals for t in (st, et)]))
        temporal_overlap_sec = 0.0
        peak_concurrency = 0

        for i in range(len(events) - 1):
            t_mid = (events[i] + events[i + 1]) / 2.0
            active_count = sum(1 for st, et in intervals if st <= t_mid <= et)
            if active_count > peak_concurrency:
                peak_concurrency = active_count
            if active_count >= 2:
                temporal_overlap_sec += (events[i + 1] - events[i])

        return timeline, peak_concurrency, temporal_overlap_sec

    def finalize_audit(
        self,
        conversation_id: str,
        transcript_path: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> AuditFinalResult:
        """
        Executes complete post-execution transcript audit.
        Evaluates Final Compliance, detects deviations, updates session, and archives history.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        session_path = self._get_session_path(conversation_id)

        # Resolve transcript path
        if not transcript_path:
            transcript_path = os.path.join(
                self.brain_root, conversation_id, ".system_generated", "logs", "transcript.jsonl"
            )

        with SessionLock(self.locks_dir, conversation_id):
            session_data: Dict[str, Any] = {}
            if os.path.isfile(session_path):
                try:
                    with open(session_path, "r", encoding="utf-8") as f:
                        session_data = json.load(f)
                except Exception:
                    session_data = {}

            effective_task_id = task_id or session_data.get("ACTIVE_TASK_ID", "default_task")
            tasks_map = session_data.get("TASKS", {})
            task_record = tasks_map.get(effective_task_id, {})

            policy_id = session_data.get("POLICY_ID", "UNBOUND")
            planned_strategy_str = session_data.get("PLANNED_STRATEGY", session_data.get("TASK_SIZING_DECISION", "INLINE"))
            planned_strategy = SizingStrategy(planned_strategy_str) if planned_strategy_str in SizingStrategy.__members__ else SizingStrategy.INLINE
            required_workers = session_data.get("REQUIRED_WORKERS", 0)

            provisional_comp_str = session_data.get("POLICY_COMPLIANCE", ProvisionalComplianceStatus.PENDING.value)
            try:
                provisional_compliance = ProvisionalComplianceStatus(provisional_comp_str)
            except Exception:
                provisional_compliance = ProvisionalComplianceStatus.UNKNOWN

            # Full transcript parsing
            timeline, peak_concurrency, temporal_overlap_sec = self._extract_timeline_and_concurrency(transcript_path)
            actual_workers = len(timeline)

            # Classify executed strategy
            if actual_workers == 0:
                executed_strategy = SizingStrategy.INLINE
            elif actual_workers == 1:
                executed_strategy = SizingStrategy.BATCH
            else:
                if peak_concurrency >= 2 and temporal_overlap_sec > 0.0:
                    executed_strategy = SizingStrategy.PARALLEL
                else:
                    # Serialized waterfall
                    executed_strategy = SizingStrategy.BATCH

            # Evaluate Final Compliance & Specific Deviation Type
            final_compliance = FinalComplianceStatus.PASS
            deviation_type = DeviationType.NONE
            deviation_details = None

            if planned_strategy == SizingStrategy.INLINE:
                if actual_workers > 0:
                    final_compliance = FinalComplianceStatus.DEVIATION
                    deviation_type = DeviationType.INLINE_WITH_SUBAGENTS
                    deviation_details = f"Policy planned INLINE (0 workers), but {actual_workers} subagents were dispatched."
                else:
                    final_compliance = FinalComplianceStatus.PASS

            elif planned_strategy == SizingStrategy.BATCH:
                if actual_workers == 0:
                    final_compliance = FinalComplianceStatus.DEVIATION
                    deviation_type = DeviationType.BATCH_ZERO_WORKERS
                    deviation_details = "Policy planned BATCH (1 dedicated worker), but 0 subagents were dispatched."
                elif actual_workers == 1:
                    final_compliance = FinalComplianceStatus.PASS
                else:
                    final_compliance = FinalComplianceStatus.DEVIATION
                    deviation_type = DeviationType.BATCH_MULTIPLE_WORKERS
                    deviation_details = f"Policy planned BATCH (1 worker), but {actual_workers} subagents were dispatched."

            elif planned_strategy == SizingStrategy.PARALLEL:
                if actual_workers < 2:
                    final_compliance = FinalComplianceStatus.DEVIATION
                    deviation_type = DeviationType.PARALLEL_INSUFFICIENT_WORKERS
                    deviation_details = f"Policy planned PARALLEL (>= 2 workers), but only {actual_workers} workers were dispatched."
                elif peak_concurrency < 2 or temporal_overlap_sec == 0.0:
                    final_compliance = FinalComplianceStatus.DEVIATION
                    deviation_type = DeviationType.PARALLEL_SERIALIZED_NO_OVERLAP
                    deviation_details = (
                        f"Policy planned PARALLEL, {actual_workers} workers dispatched, but execution was serialized "
                        f"(concurrency peak: {peak_concurrency}, temporal overlap: {temporal_overlap_sec:.2f}s)."
                    )
                else:
                    final_compliance = FinalComplianceStatus.PASS

            audit_result = AuditFinalResult(
                policy_id=policy_id,
                conversation_id=conversation_id,
                task_id=effective_task_id,
                planned_strategy=planned_strategy,
                executed_strategy=executed_strategy,
                required_workers=required_workers,
                actual_workers=actual_workers,
                concurrency_peak=peak_concurrency,
                temporal_overlap_sec=temporal_overlap_sec,
                provisional_compliance=provisional_compliance,
                final_compliance=final_compliance,
                deviation_type=deviation_type,
                deviation_details=deviation_details,
                timeline=timeline,
                verified_at=now_utc
            )

            # Update session state with final audit
            session_data["FINAL_AUDIT"] = audit_result.to_dict()
            session_data["ACTUAL_WORKERS"] = actual_workers
            session_data["CONCURRENCY_PEAK"] = peak_concurrency
            session_data["TEMPORAL_OVERLAP_SEC"] = round(temporal_overlap_sec, 2)
            session_data["FINAL_COMPLIANCE"] = final_compliance.value
            session_data["DEVIATION_TYPE"] = deviation_type.value
            session_data["LAST_UPDATED"] = now_utc

            if task_record:
                task_record["FINAL_AUDIT"] = audit_result.to_dict()
                task_record["FINAL_COMPLIANCE"] = final_compliance.value
                task_record["DEVIATION_TYPE"] = deviation_type.value
                task_record["UPDATED_AT"] = now_utc

            self._atomic_write_json(session_path, session_data)

            # Record final audit in lifecycle log
            self._append_jsonl_log("policy_lifecycle.jsonl", {
                "EVENT": "AUDIT_FINALIZED",
                "TIMESTAMP": now_utc,
                "CONVERSATION_ID": conversation_id,
                "TASK_ID": effective_task_id,
                "POLICY_ID": policy_id,
                "PLANNED_STRATEGY": planned_strategy.value,
                "EXECUTED_STRATEGY": executed_strategy.value,
                "ACTUAL_WORKERS": actual_workers,
                "CONCURRENCY_PEAK": peak_concurrency,
                "TEMPORAL_OVERLAP_SEC": round(temporal_overlap_sec, 2),
                "PROVISIONAL_COMPLIANCE": provisional_compliance.value,
                "FINAL_COMPLIANCE": final_compliance.value,
                "DEVIATION_TYPE": deviation_type.value,
                "DEVIATION_DETAILS": deviation_details
            })

            # Historical archive snapshot
            history_filename = f"{conversation_id}_{effective_task_id}_{int(time.time())}.json"
            history_path = os.path.join(self.history_dir, history_filename)
            self._atomic_write_json(history_path, session_data)

            return audit_result

    # -------------------------------------------------------------------------
    # Lifecycle Hook Entrypoints (SessionStart, PreToolUse, Stop)
    # -------------------------------------------------------------------------

    def handle_session_start(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Lifecycle hook handler for SessionStart event."""
        try:
            conv_id = payload.get("conversationId", f"sess-{uuid.uuid4().hex[:8]}")
            user_input = payload.get("lastUserInput", "")
            workspace_paths = payload.get("workspacePaths", [])

            self.create_and_bind_policy(
                conversation_id=conv_id,
                task_input=user_input,
                workspace_paths=workspace_paths
            )
        except Exception:
            pass
        return {}

    def handle_pre_tool_use(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Lifecycle hook handler for PreToolUse event."""
        try:
            return self.record_tool_dispatch(payload)
        except Exception as e:
            # Absolute fail-open fallback
            return {
                "decision": "allow",
                "reason": f"Execution Policy (AUDIT Fallback): {e}"
            }

    def handle_stop(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Lifecycle hook handler for Stop event."""
        try:
            conv_id = payload.get("conversationId", "UNKNOWN")
            transcript_path = payload.get("transcriptPath")
            self.finalize_audit(conversation_id=conv_id, transcript_path=transcript_path)
        except Exception:
            pass
        return {}


def main():
    """CLI dispatcher for testing and hook delegation."""
    import argparse
    parser = argparse.ArgumentParser(description="Policy Lifecycle Manager CLI")
    subparsers = parser.add_subparsers(dest="command")

    # analyze
    analyze_p = subparsers.add_parser("analyze")
    analyze_p.add_argument("--prompt", required=True)

    # create-policy
    create_p = subparsers.add_parser("create-policy")
    create_p.add_argument("--conv-id", required=True)
    create_p.add_argument("--prompt", required=True)
    create_p.add_argument("--task-id")

    # finalize
    fin_p = subparsers.add_parser("finalize")
    fin_p.add_argument("--conv-id", required=True)
    fin_p.add_argument("--transcript-path")

    # hook-session-start
    subparsers.add_parser("hook-session-start")

    # hook-pre-tool-use
    subparsers.add_parser("hook-pre-tool-use")

    # hook-stop
    subparsers.add_parser("hook-stop")

    args = parser.parse_args()
    mgr = PolicyLifecycleManager()

    if args.command == "analyze":
        char = AutomatedTaskAnalyzer.analyze(args.prompt)
        print(json.dumps(asdict(char), indent=2))

    elif args.command == "create-policy":
        pol = mgr.create_and_bind_policy(args.conv_id, args.prompt, task_id=args.task_id)
        print(json.dumps(pol.to_dict(), indent=2))

    elif args.command == "finalize":
        res = mgr.finalize_audit(args.conv_id, transcript_path=args.transcript_path)
        print(json.dumps(res.to_dict(), indent=2))

    elif args.command in ("hook-session-start", "hook-pre-tool-use", "hook-stop"):
        try:
            raw = sys.stdin.read().strip()
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}

        try:
            if args.command == "hook-session-start":
                out = mgr.handle_session_start(payload)
            elif args.command == "hook-pre-tool-use":
                out = mgr.handle_pre_tool_use(payload)
            else:
                out = mgr.handle_stop(payload)
        except Exception as e:
            if args.command == "hook-pre-tool-use":
                out = {"decision": "allow", "reason": f"Audit fallback: {e}"}
            else:
                out = {}

        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
