import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class SpanBase(BaseModel):
    trace_id: str = Field(..., max_length=64)
    span_id: str = Field(..., max_length=32)
    parent_span_id: Optional[str] = Field(None, max_length=32)
    service_name: str = Field(..., max_length=64)
    operation_name: str = Field(..., max_length=128)
    start_time_ns: int
    end_time_ns: int
    duration_ms: float
    status_code: str = "UNSET"
    http_status_code: Optional[int] = None
    error_message: Optional[str] = None
    attributes_json: Optional[str] = None
    events_json: Optional[str] = None


class SpanCreate(SpanBase):
    incident_id: Optional[str] = None


class SpanRead(SpanBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: Optional[str] = None
    created_at: datetime.datetime


class TraceDAGNode(BaseModel):
    span: SpanRead
    children: List["TraceDAGNode"] = []


TraceDAGNode.model_rebuild()
