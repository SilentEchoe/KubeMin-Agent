from pydantic import BaseModel, Field, UUID4, validator
from typing import List, Optional, Any, Dict, Literal
from uuid import uuid4
from datetime import datetime
import enum

# --- Enums ---

class Severity(str, enum.Enum):
    S0 = "S0" # Info / No Issue
    S1 = "S1" # Availability Impact
    S2 = "S2" # Performance Impact
    S3 = "S3" # Minor / Suggestion

class ToolType(str, enum.Enum):
    K8S_PODS = "k8s_pods"
    K8S_LOGS = "k8s_logs"
    PROM_QUERY = "prom_query"

# --- Evidence & Issues ---

class Evidence(BaseModel):
    source: str = Field(..., description="Source of the evidence, e.g., 'k8s_pods', 'prom'")
    ref: str = Field(..., description="Reference, e.g., pod name or metric query")
    value: str = Field(..., description="The evidence value or summary")

class Recommendation(BaseModel):
    action: str = Field(..., description="Recommended action")
    commands: List[str] = Field(default_factory=list, description="Suggest commands to run")
    confidence: float = Field(default=1.0, description="Confidence score 0.0-1.0")

class Issue(BaseModel):
    id: str = Field(..., description="Unique issue ID")
    title: str = Field(..., description="Short title of the issue")
    severity: Severity = Field(default=Severity.S3)
    hypothesis: str = Field(..., description="Explanation of why this issue is happening")
    evidence: List[Evidence] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)

# --- Report Components ---

class ToolCallRecord(BaseModel):
    tool: str
    pk: bool
    latency_ms: float
    error_type: Optional[str] = None
    
class MetricHighlight(BaseModel):
    name: str
    expr: str
    highlights: List[str]

class RunLimits(BaseModel):
    log_truncated: bool = False
    prom_partial: bool = False

class RunMeta(BaseModel):
    prompt_version: str = "v1"
    model: str = "unknown"
    token_usage: Dict[str, int] = Field(default_factory=lambda: {"input": 0, "output": 0})
    
# --- Top Level Objects ---

class RunInput(BaseModel):
    query: str
    app_id: str
    namespace: str = "default"
    run_id: UUID4 = Field(default_factory=uuid4)

class RunSummary(BaseModel):
    severity: Severity
    headline: str
    top_findings: List[str]

class RunReport(BaseModel):
    """
    The structured output of a diagnostic run.
    This is the core contract for the Enterprise Agent.
    """
    run_id: UUID4
    input: RunInput
    summary: RunSummary
    issues: List[Issue] = Field(default_factory=list)
    metrics: List[MetricHighlight] = Field(default_factory=list)
    
    # Audit & Telemetry
    tool_calls: List[ToolCallRecord] = Field(default_factory=list, alias="toolCalls")
    limits: RunLimits = Field(default_factory=RunLimits)
    meta: RunMeta = Field(default_factory=RunMeta)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
