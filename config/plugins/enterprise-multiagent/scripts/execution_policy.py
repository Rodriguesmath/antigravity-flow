"""
Deterministic Execution Policy and Independent Transcript Verifier
Antigravity Multi-Agent Runtime Architecture

Defines:
- ExecutionPolicy: Schema specifying planned topology, required workers, allowed tools, and fallback.
- ExecutionPolicyVerifier: Independent verifier that inspects actual conversation transcripts,
  determines the executed strategy (INLINE, BATCH, PARALLEL with temporal overlap),
  and certifies compliance (PASS, DEVIATION, UNKNOWN).
"""
import os
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple

from task_sizing_gate import SizingStrategy, ConfidenceLevel, SizingDecision

class ComplianceStatus(str, Enum):
    PASS = "PASS"
    DEVIATION = "DEVIATION"
    UNKNOWN = "UNKNOWN"

class EnforcementMode(str, Enum):
    ENFORCED = "ENFORCED"  # Structurally or hook-enforced by the runtime
    ADVISORY = "ADVISORY"  # Communicated via prompt; model retains tool capability to deviate

@dataclass
class ExecutionPolicy:
    policy_id: str
    task_sizing_decision: SizingStrategy
    required_workers: int
    allowed_tools: List[str]
    estimated_speedup: float
    estimation_confidence: ConfidenceLevel
    fallback_strategy: SizingStrategy
    enforcement_mode: EnforcementMode = EnforcementMode.ADVISORY
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "POLICY_ID": self.policy_id,
            "TASK_SIZING_DECISION": self.task_sizing_decision.value,
            "REQUIRED_WORKERS": self.required_workers,
            "ALLOWED_TOOLS": self.allowed_tools,
            "ESTIMATED_SPEEDUP": round(self.estimated_speedup, 3),
            "ESTIMATION_CONFIDENCE": self.estimation_confidence.value,
            "FALLBACK_STRATEGY": self.fallback_strategy.value,
            "ENFORCEMENT_MODE": self.enforcement_mode.value,
            "NOTES": self.notes
        }

@dataclass
class PolicyVerificationResult:
    policy_id: str
    planned_strategy: SizingStrategy
    executed_strategy: SizingStrategy
    required_workers: int
    actual_workers: int
    concurrency_peak: int
    policy_compliance: ComplianceStatus
    enforcement_mode: EnforcementMode
    temporal_overlap_proven: bool
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    deviation_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "POLICY_ID": self.policy_id,
            "PLANNED_STRATEGY": self.planned_strategy.value,
            "EXECUTED_STRATEGY": self.executed_strategy.value,
            "REQUIRED_WORKERS": self.required_workers,
            "ACTUAL_WORKERS": self.actual_workers,
            "CONCURRENCY_PEAK": self.concurrency_peak,
            "POLICY_COMPLIANCE": self.policy_compliance.value,
            "ENFORCEMENT_MODE": self.enforcement_mode.value,
            "TEMPORAL_OVERLAP_PROVEN": self.temporal_overlap_proven,
            "DEVIATION_REASON": self.deviation_reason
        }

class PolicyFactory:
    """Creates deterministic execution policies from task sizing decisions."""

    BASE_TOOLS = ["read_file", "run_command", "manage_task"]
    FILE_EDITING_TOOLS = ["edit_file", "write_file"]
    SUBAGENT_TOOLS = ["invoke_subagent", "manage_subagents", "send_message", "define_subagent"]

    @classmethod
    def create_policy(cls, decision: SizingDecision, task_id: str) -> ExecutionPolicy:
        policy_id = f"POL-{task_id}-{decision.strategy.value}"

        if decision.strategy == SizingStrategy.INLINE:
            # INLINE: Single agent with file editing, strictly zero subagents
            # When routed via flash-implementer, this is structurally ENFORCED
            return ExecutionPolicy(
                policy_id=policy_id,
                task_sizing_decision=SizingStrategy.INLINE,
                required_workers=0,
                allowed_tools=cls.BASE_TOOLS + cls.FILE_EDITING_TOOLS,
                estimated_speedup=decision.expected_speedup,
                estimation_confidence=decision.estimation_confidence,
                fallback_strategy=SizingStrategy.INLINE,
                enforcement_mode=EnforcementMode.ENFORCED,
                notes="Executed inline directly. Subagent tools structurally withheld."
            )

        elif decision.strategy == SizingStrategy.BATCH:
            # BATCH: Exactly 1 dedicated worker
            # Because default orchestrator retains subagent tools, topology is ADVISORY
            return ExecutionPolicy(
                policy_id=policy_id,
                task_sizing_decision=SizingStrategy.BATCH,
                required_workers=1,
                allowed_tools=cls.BASE_TOOLS + cls.SUBAGENT_TOOLS,
                estimated_speedup=decision.expected_speedup,
                estimation_confidence=decision.estimation_confidence,
                fallback_strategy=SizingStrategy.INLINE,
                enforcement_mode=EnforcementMode.ADVISORY,
                notes="Batched to exactly 1 dedicated implementer worker. Prompt-mandated."
            )

        else: # PARALLEL
            # PARALLEL: Multi-worker fan-out (2 to 4 workers) with temporal overlap
            # ADVISORY unless orchestrator file-writing is structurally disabled
            return ExecutionPolicy(
                policy_id=policy_id,
                task_sizing_decision=SizingStrategy.PARALLEL,
                required_workers=4,
                allowed_tools=cls.BASE_TOOLS + cls.SUBAGENT_TOOLS,
                estimated_speedup=decision.expected_speedup,
                estimation_confidence=decision.estimation_confidence,
                fallback_strategy=SizingStrategy.BATCH,
                enforcement_mode=EnforcementMode.ADVISORY,
                notes="Parallel Dynamic DAG fan-out. Topologically ADVISORY."
            )

class ExecutionPolicyVerifier:
    """
    Independent Verifier that compares planned ExecutionPolicy against actual
    conversation transcripts on disk, evaluating workers, concurrency, and strategy.
    """

    def __init__(self, brain_root: Optional[str] = None):
        self.brain_root = brain_root or os.path.expanduser("~/.gemini/antigravity-cli/brain")

    def _extract_timeline_from_transcript(self, transcript_path: str) -> Tuple[List[Dict[str, Any]], int]:
        """Parses transcript.jsonl to extract subagent lifespans and true peak concurrency."""
        if not os.path.isfile(transcript_path):
            return [], 0

        subagents_map: Dict[int, Dict[str, Any]] = {}
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                created_at = data.get("created_at", "")
                step_index = data.get("step_index")
                content = data.get("content", "")

                # Detect invoke_subagent calls
                for tc in data.get("tool_calls", []):
                    if tc.get("name") in ["invoke_subagent", "delegate_task"]:
                        role = tc.get("args", {}).get("Role", "Unknown")
                        subagents_map[step_index] = {
                            "step_index": step_index,
                            "role": role,
                            "start": created_at,
                            "conv_id": None,
                            "end": None
                        }

                # Detect subagent conversation ID
                if "conversation ID: `" in content or "conversationId" in content:
                    for s_idx, s_data in subagents_map.items():
                        if s_data["conv_id"] is None and "conversation ID: `" in content:
                            try:
                                cid = content.split("conversation ID: `")[1].split("`")[0]
                                s_data["conv_id"] = cid
                            except Exception:
                                pass
                            break

                # Detect subagent completion notification
                if "Notification details:" in content and "From: Subagent" in content:
                    for s_idx, s_data in subagents_map.items():
                        if s_data["conv_id"] and s_data["conv_id"] in content and s_data["end"] is None:
                            s_data["end"] = created_at
                            break

        # Calculate peak overlapping concurrency
        active_intervals = []
        for s_idx, s_data in subagents_map.items():
            start = s_data.get("start")
            end = s_data.get("end")
            if start and end:
                active_intervals.append((start, end))

        max_concurrency = 0
        for start_str, end_str in active_intervals:
            overlap = sum(1 for s, e in active_intervals if s <= start_str <= e)
            if overlap > max_concurrency:
                max_concurrency = overlap

        timeline = list(subagents_map.values())
        peak = max(1, max_concurrency) if timeline else 1
        return timeline, peak

    def verify(
        self,
        policy: ExecutionPolicy,
        conversation_id: str,
        transcript_override_path: Optional[str] = None
    ) -> PolicyVerificationResult:
        if transcript_override_path:
            tpath = transcript_override_path
        else:
            tpath = os.path.join(self.brain_root, conversation_id, ".system_generated", "logs", "transcript.jsonl")

        if not os.path.isfile(tpath):
            return PolicyVerificationResult(
                policy_id=policy.policy_id,
                planned_strategy=policy.task_sizing_decision,
                executed_strategy=SizingStrategy.INLINE,
                required_workers=policy.required_workers,
                actual_workers=0,
                concurrency_peak=0,
                policy_compliance=ComplianceStatus.UNKNOWN,
                enforcement_mode=policy.enforcement_mode,
                temporal_overlap_proven=False,
                deviation_reason=f"Transcript not found at {tpath}"
            )

        timeline, peak_concurrency = self._extract_timeline_from_transcript(tpath)
        actual_workers = len(timeline)

        # Classify executed strategy based on empirical evidence:
        # 1. INLINE: zero subagents invoked.
        # 2. BATCH: exactly one subagent invoked.
        # 3. PARALLEL: multiple subagents (>= 2) with proven temporal overlap (peak >= 2).
        temporal_overlap_proven = False
        if actual_workers == 0:
            executed_strategy = SizingStrategy.INLINE
        elif actual_workers == 1:
            executed_strategy = SizingStrategy.BATCH
        else:
            # 2 or more subagents
            if peak_concurrency >= 2:
                executed_strategy = SizingStrategy.PARALLEL
                temporal_overlap_proven = True
            else:
                # Multiple subagents were run serialized in cascade, not in parallel
                executed_strategy = SizingStrategy.BATCH
                temporal_overlap_proven = False

        # Evaluate Compliance:
        compliance = ComplianceStatus.PASS
        deviation_reason = None

        if executed_strategy != policy.task_sizing_decision:
            compliance = ComplianceStatus.DEVIATION
            deviation_reason = (
                f"Policy planned {policy.task_sizing_decision.value} (requires {policy.required_workers} workers), "
                f"but agent executed {executed_strategy.value} ({actual_workers} workers observed, peak concurrency {peak_concurrency})."
            )
        elif policy.task_sizing_decision == SizingStrategy.PARALLEL and not temporal_overlap_proven:
            compliance = ComplianceStatus.DEVIATION
            deviation_reason = "Multiple workers spawned but execution was serialized (no temporal overlap)."

        return PolicyVerificationResult(
            policy_id=policy.policy_id,
            planned_strategy=policy.task_sizing_decision,
            executed_strategy=executed_strategy,
            required_workers=policy.required_workers,
            actual_workers=actual_workers,
            concurrency_peak=peak_concurrency,
            policy_compliance=compliance,
            enforcement_mode=policy.enforcement_mode,
            temporal_overlap_proven=temporal_overlap_proven,
            timeline=timeline,
            deviation_reason=deviation_reason
        )
