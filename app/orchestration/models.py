from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    WORKFLOW = "workflow"


class PlanStepType(str, Enum):
    SINGLE = "single"
    MULTI = "multi"


class ConsensusStrategy(str, Enum):
    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_SCORE = "weighted_score"
    HIGHEST_CONFIDENCE = "highest_confidence"
    FIRST_SUCCESS = "first_success"
    BEST_LATENCY = "best_latency"
    BEST_QUALITY = "best_quality"


class WorkflowNodeType(str, Enum):
    TASK = "task"
    IF = "if"
    ELSE = "else"
    FOR = "for"
    PARALLEL = "parallel"
    WAIT = "wait"
    RETRY = "retry"
    TIMEOUT = "timeout"
    MERGE = "merge"
    CONDITIONAL = "conditional"
    START = "start"
    END = "end"


class PlanStep(BaseModel):
    step: str = ""
    agent: str = "chat"
    execution: str = "sequential"
    prompt_template: str = ""
    tools: list[str] = Field(default_factory=list)
    timeout: float = 60.0
    retry_count: int = 0
    provider: str = ""
    model: str = ""
    context_refs: list[str] = Field(default_factory=list)
    depends_on: list[int] = Field(default_factory=list)
    merge_strategy: str = "concat"


class ExecutionPlan(BaseModel):
    steps: list[PlanStep] = Field(default_factory=list)
    plan_id: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


@dataclass
class AgentResult:
    agent: str
    step: str
    content: str
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    tokens: int = 0
    cost: float = 0.0
    success: bool = True
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectionScore:
    correctness: float = 0.0
    hallucination: float = 0.0
    completeness: float = 0.0
    overall: float = 0.0
    should_retry: bool = False
    reason: str = ""


@dataclass
class ConsensusResult:
    provider: str
    model: str
    content: str
    strategy: str
    scores: dict[str, float] = field(default_factory=dict)
    votes: int = 0
    total_votes: int = 0


@dataclass
class DebateResult:
    provider_a: str
    provider_b: str
    argument_a: str
    argument_b: str
    final_content: str
    winner: str = ""
    reviewer_notes: str = ""


@dataclass
class VoteScore:
    quality: float = 0.0
    cost: float = 0.0
    latency: float = 0.0
    reliability: float = 0.0
    overall: float = 0.0


class WorkflowStep(BaseModel):
    id: str = ""
    type: WorkflowNodeType = WorkflowNodeType.TASK
    agent: str = ""
    prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    condition: str = ""
    variable: str = ""
    collection: str = ""
    steps: list[WorkflowStep] = Field(default_factory=list)
    retry_count: int = 0
    timeout: float = 60.0
    merge_strategy: str = "concat"
    depends_on: list[str] = Field(default_factory=list)
    parallel_branch: str = ""


class WorkflowDefinition(BaseModel):
    id: str = ""
    steps: list[WorkflowStep] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


@dataclass
class WorkflowResult:
    workflow_id: str
    outputs: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str = ""


class ToolDefinition(BaseModel):
    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    timeout: int = 30


class OrchestrationRequest(BaseModel):
    prompt: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = "single"
    agents: list[str] = Field(default_factory=list)
    workflow: WorkflowDefinition | None = None
    consensus: bool = False
    consensus_providers: list[str] = Field(default_factory=list)
    consensus_strategy: str = "majority_vote"
    debate: bool = False
    debate_provider_a: str = ""
    debate_provider_b: str = ""
    reflection: bool = False
    reflection_threshold: float = 0.7
    parallel: bool = False
    stream: bool = False
    model: str = ""
    provider: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout: int = 120


class OrchestrationResponse(BaseModel):
    id: str = ""
    content: str = ""
    plan: ExecutionPlan | None = None
    results: list[AgentResult] = Field(default_factory=list)
    reflection: ReflectionScore | None = None
    consensus: ConsensusResult | None = None
    debate: DebateResult | None = None
    workflow: WorkflowResult | None = None
    latency_ms: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0
    mode: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    graph: dict[str, Any] = Field(default_factory=dict)
