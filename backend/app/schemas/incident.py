import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class IncidentBase(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    severity: str = Field(default="HIGH", max_length=16)
    suspect_service: Optional[str] = None


class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
    suspect_service: Optional[str] = None
    root_cause_summary: Optional[str] = None
    blast_radius_json: Optional[str] = None
    postmortem_markdown: Optional[str] = None
    pull_request_json: Optional[str] = None
    resolved_at: Optional[datetime.datetime] = None
    closed_at: Optional[datetime.datetime] = None


class IncidentRead(IncidentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    root_cause_summary: Optional[str] = None
    blast_radius_json: Optional[str] = None
    postmortem_markdown: Optional[str] = None
    pull_request_json: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    resolved_at: Optional[datetime.datetime] = None
    closed_at: Optional[datetime.datetime] = None
