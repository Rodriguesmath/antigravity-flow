"""
Adaptive Task Sizing Gate for Antigravity Multi-Agent Harness
Decides execution strategy (INLINE, BATCH, PARALLEL) based on empirical cost modeling,
coordination tax, module independence, and risk factors.
Preserves Dynamic DAG, Speculative QA, Semantic Reconciliation, and Adaptive Concurrency.
"""
import os
import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, Any, Optional

def load_feature_flags() -> Dict[str, Any]:
    flags_path = os.path.expanduser("~/.gemini/config/flags.json")
    flags = {
        "ADAPTIVE_TASK_SIZING_ENABLED": True,
        "MIN_SPEEDUP_MARGIN": 1.20,
        "SUBAGENT_TAX_PER_WORKER_SEC": 25.0,
        "SUBAGENT_SEQ_TAX_SEC": 22.0,
        "SUBAGENT_CONCURRENT_STARTUP_SEC": 6.0,
        "ORCHESTRATOR_BASE_TAX_SEC": 20.0,
        "GATEKEEPER_TAX_SEC": 20.0,
        "MAX_PARALLEL_WORKERS": 4
    }
    if os.path.exists(flags_path):
        try:
            with open(flags_path, "r", encoding="utf-8") as f:
                file_flags = json.load(f)
                flags.update(file_flags)
        except Exception:
            pass

    # Environment variables override
    env_enabled = os.environ.get("ADAPTIVE_TASK_SIZING_ENABLED")
    if env_enabled is not None:
        flags["ADAPTIVE_TASK_SIZING_ENABLED"] = env_enabled.lower() in ("true", "1", "yes")

    env_margin = os.environ.get("MIN_SPEEDUP_MARGIN")
    if env_margin is not None:
        try:
            flags["MIN_SPEEDUP_MARGIN"] = float(env_margin)
        except ValueError:
            pass

    return flags

class SizingStrategy(str, Enum):
    INLINE = "INLINE"      # Executed directly by orchestrator (zero subagents)
    BATCH = "BATCH"        # Tasks batched into a single dedicated implementer worker
    PARALLEL = "PARALLEL"  # Distributed fan-out to parallel workers via Dynamic DAG

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

@dataclass
class TaskCharacteristics:
    task_id: str
    module_count: int               # Number of distinct modules/files to be modified
    complexity_score: int           # 1 (Trivial/Bugfix) to 5 (Heavy Algorithmic/Architecture)
    dependency_ratio: float         # 0.0 (Fully independent) to 1.0 (Strictly chained)
    estimated_work_sec_per_module: Optional[float] = None # Prior estimate if known
    has_historical_data: bool = True
    historical_cv: float = 0.15     # Historical Coefficient of Variation
    security_risk: bool = False     # Requires dedicated security audit gatekeeper

@dataclass
class SizingDecision:
    strategy: SizingStrategy
    estimated_single_time: float
    estimated_multi_time: float
    expected_speedup: float
    estimation_confidence: ConfidenceLevel
    coordination_tax_sec: float
    rationale: str
    actual_speedup: Optional[str] = "N/A"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "TASK_SIZING_DECISION": self.strategy.value,
            "ESTIMATED_SINGLE_TIME": round(self.estimated_single_time, 2),
            "ESTIMATED_MULTI_TIME": round(self.estimated_multi_time, 2),
            "EXPECTED_SPEEDUP": round(self.expected_speedup, 3),
            "ESTIMATION_CONFIDENCE": self.estimation_confidence.value,
            "ACTUAL_SPEEDUP": self.actual_speedup,
            "COORDINATION_TAX_SEC": round(self.coordination_tax_sec, 2),
            "RATIONALE": self.rationale
        }

class AdaptiveTaskSizingGate:
    """
    Evaluates whether delegating a task to subagents produces a real net gain,
    accounting for prompt contract authoring, cold-start, handshake, and straggler risk.
    """
    def __init__(
        self,
        min_speedup_margin: Optional[float] = None,
        subagent_tax_per_worker: Optional[float] = None,
        subagent_seq_tax: Optional[float] = None,
        subagent_concurrent_startup: Optional[float] = None,
        orchestrator_base_tax: Optional[float] = None,
        gatekeeper_tax: Optional[float] = None,
        max_parallel_workers: Optional[int] = None,
        enabled: Optional[bool] = None
    ):
        flags = load_feature_flags()
        self.enabled = flags.get("ADAPTIVE_TASK_SIZING_ENABLED", True) if enabled is None else enabled
        self.min_speedup_margin = flags.get("MIN_SPEEDUP_MARGIN", 1.20) if min_speedup_margin is None else min_speedup_margin
        self.subagent_tax_per_worker = flags.get("SUBAGENT_TAX_PER_WORKER_SEC", 25.0) if subagent_tax_per_worker is None else subagent_tax_per_worker
        
        # Decompose subagent tax into sequential (critical-path authoring + review) and concurrent (parallel boot)
        if subagent_seq_tax is not None:
            self.subagent_seq_tax_per_worker = subagent_seq_tax
        elif "SUBAGENT_SEQ_TAX_SEC" in flags:
            self.subagent_seq_tax_per_worker = flags["SUBAGENT_SEQ_TAX_SEC"]
        else:
            self.subagent_seq_tax_per_worker = 22.0

        if subagent_concurrent_startup is not None:
            self.subagent_concurrent_startup = subagent_concurrent_startup
        elif "SUBAGENT_CONCURRENT_STARTUP_SEC" in flags:
            self.subagent_concurrent_startup = flags["SUBAGENT_CONCURRENT_STARTUP_SEC"]
        else:
            self.subagent_concurrent_startup = 6.0

        self.orchestrator_base_tax = flags.get("ORCHESTRATOR_BASE_TAX_SEC", 20.0) if orchestrator_base_tax is None else orchestrator_base_tax
        self.gatekeeper_tax = flags.get("GATEKEEPER_TAX_SEC", 20.0) if gatekeeper_tax is None else gatekeeper_tax
        self.max_parallel_workers = flags.get("MAX_PARALLEL_WORKERS", 4) if max_parallel_workers is None else max_parallel_workers

    def _estimate_work_time(self, task: TaskCharacteristics) -> float:
        """Estimates raw implementation time in seconds per module based on complexity."""
        if task.estimated_work_sec_per_module is not None:
            return task.estimated_work_sec_per_module

        # Complexity heuristic scale (calibrated against real Flash timings)
        # Level 1 (Bugfix): ~30s-40s per module
        # Level 2 (Simple Module/Stub): ~45s-60s per module
        # Level 3 (Standard Component): ~75s-100s per module
        # Level 4 (Complex Component): ~120s-160s per module
        # Level 5 (Heavy Architecture): ~200s+ per module
        complexity_map = {
            1: 35.0,
            2: 50.0,
            3: 85.0,
            4: 140.0,
            5: 220.0
        }
        return complexity_map.get(task.complexity_score, 60.0)

    def evaluate(self, task: TaskCharacteristics) -> SizingDecision:
        # Check Feature Flag first
        if not self.enabled:
            return SizingDecision(
                strategy=SizingStrategy.PARALLEL if task.module_count > 1 else SizingStrategy.INLINE,
                estimated_single_time=0.0,
                estimated_multi_time=0.0,
                expected_speedup=1.0,
                estimation_confidence=ConfidenceLevel.HIGH,
                coordination_tax_sec=0.0,
                rationale="Feature flag ADAPTIVE_TASK_SIZING_ENABLED is false; gate disabled."
            )

        # Rule 0: Confidence Assessment
        if not task.has_historical_data or task.complexity_score not in [1, 2, 3, 4, 5]:
            confidence = ConfidenceLevel.LOW
        elif task.historical_cv > 0.40:
            confidence = ConfidenceLevel.MEDIUM  # High historical volatility
        else:
            confidence = ConfidenceLevel.HIGH

        # Baseline raw work per module
        w_module = self._estimate_work_time(task)

        # 1. Single Agent Estimation
        # T_single = Orchestrator inline exploration + sequential work across all modules
        t_single_explore = 30.0
        # Sequential implementation penalty increases if modules are chained
        sequential_work = task.module_count * w_module * (1.0 + (task.dependency_ratio * 0.15))
        t_single = t_single_explore + sequential_work

        # Special Case: Single Module Task (N = 1) -> Strictly INLINE
        if task.module_count <= 1:
            return SizingDecision(
                strategy=SizingStrategy.INLINE,
                estimated_single_time=t_single,
                estimated_multi_time=t_single + self.subagent_tax_per_worker + self.gatekeeper_tax,
                expected_speedup=1.0,
                estimation_confidence=confidence,
                coordination_tax_sec=0.0,
                rationale="Single module task (N <= 1). Fast-Path inline execution avoids all coordination overhead."
            )

        # Special Case: Strict Dependency Chain (Dependency Ratio >= 0.8) -> Cannot parallelize
        if task.dependency_ratio >= 0.8:
            return SizingDecision(
                strategy=SizingStrategy.INLINE if task.module_count <= 2 else SizingStrategy.BATCH,
                estimated_single_time=t_single,
                estimated_multi_time=t_single + (self.subagent_tax_per_worker * task.module_count),
                expected_speedup=0.85,
                estimation_confidence=confidence,
                coordination_tax_sec=self.subagent_tax_per_worker * task.module_count,
                rationale="High dependency chain (ratio >= 0.8). Modules must be serialized; parallel fan-out yields net loss."
            )

        # 2. Multi-Agent Parallel Estimation
        workers = min(task.module_count, self.max_parallel_workers)

        # In parallel mode: execution time is determined by the slowest module worker + straggler variance
        # Straggler factor scales with historical CV and worker count
        straggler_multiplier = 1.0 + (task.historical_cv * (workers / 4.0))

        # Critical-path coordination tax:
        # Distinguish strictly sequential dispatch/reconciliation vs concurrent worker startup.
        # Sequential worker tax: Orchestrator prompt contract authoring + return parsing per worker
        # Concurrent startup tax: Worker process spawn/boot (occurs in parallel across workers, scaled by straggler)
        concurrent_startup_tax = (self.subagent_concurrent_startup * straggler_multiplier) if workers > 0 else 0.0
        sequential_worker_tax = workers * self.subagent_seq_tax_per_worker
        coordination_tax = (
            self.orchestrator_base_tax +
            sequential_worker_tax +
            concurrent_startup_tax +
            (self.gatekeeper_tax if task.security_risk or workers > 1 else 0.0)
        )

        parallel_work = (w_module * (1.0 - task.dependency_ratio)) * straggler_multiplier
        t_multi_parallel = coordination_tax + parallel_work

        expected_speedup_parallel = t_single / t_multi_parallel if t_multi_parallel > 0 else 0.0

        # 3. Batch Worker Estimation (1 dedicated worker receives all N modules in batch + 1 QA)
        batch_coordination_tax = (
            self.orchestrator_base_tax +
            self.subagent_seq_tax_per_worker +
            self.subagent_concurrent_startup +
            self.gatekeeper_tax
        )
        t_multi_batch = batch_coordination_tax + (task.module_count * w_module * 0.90)
        expected_speedup_batch = t_single / t_multi_batch if t_multi_batch > 0 else 0.0

        # Rule 4: Conservative Decision Rule
        # If confidence is LOW, reject PARALLEL and fallback to INLINE or BATCH
        if confidence == ConfidenceLevel.LOW:
            strategy = SizingStrategy.INLINE if task.module_count <= 2 else SizingStrategy.BATCH
            return SizingDecision(
                strategy=strategy,
                estimated_single_time=t_single,
                estimated_multi_time=t_multi_parallel,
                expected_speedup=expected_speedup_parallel,
                estimation_confidence=confidence,
                coordination_tax_sec=coordination_tax,
                rationale="Low confidence in estimation data. Applying conservative fallback to avoid runaway multi-agent overhead."
            )

        # Parallel Decision Threshold:
        # Requires expected speedup >= min_speedup_margin (default: 1.20, or 20% net acceleration)
        if expected_speedup_parallel >= self.min_speedup_margin:
            return SizingDecision(
                strategy=SizingStrategy.PARALLEL,
                estimated_single_time=t_single,
                estimated_multi_time=t_multi_parallel,
                expected_speedup=expected_speedup_parallel,
                estimation_confidence=confidence,
                coordination_tax_sec=coordination_tax,
                rationale=f"Decoupled parallel modules with expected speedup ({expected_speedup_parallel:.2f}x) >= margin threshold ({self.min_speedup_margin}x)."
            )

        # Batch Decision Threshold:
        # If parallel speedup < 1.20, check if batching overcomes coordination tax
        if expected_speedup_batch >= self.min_speedup_margin:
            return SizingDecision(
                strategy=SizingStrategy.BATCH,
                estimated_single_time=t_single,
                estimated_multi_time=t_multi_batch,
                expected_speedup=expected_speedup_batch,
                estimation_confidence=confidence,
                coordination_tax_sec=batch_coordination_tax,
                rationale=f"Batching multiple small modules into 1 dedicated worker avoids 4x handoff overhead ({expected_speedup_batch:.2f}x speedup)."
            )

        # Default to INLINE if neither parallel nor batch beats the single agent margin
        return SizingDecision(
            strategy=SizingStrategy.INLINE,
            estimated_single_time=t_single,
            estimated_multi_time=t_multi_parallel,
            expected_speedup=expected_speedup_parallel,
            estimation_confidence=confidence,
            coordination_tax_sec=coordination_tax,
            rationale=f"Work volume per module is insufficient to absorb coordination tax ({coordination_tax:.1f}s). Retaining task inline."
        )
