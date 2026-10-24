import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AuditEventBase(BaseModel):
    event_type: str = Field(..., max_length=64)
    actor: str = Field(default="SYSTEM", max_length=64)
    details_json: Optional[str] = None


class AuditEventCreate(AuditEventBase):
    incident_id: Optional[str] = None


class AuditEventRead(AuditEventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: Optional[str] = None
    created_at: datetime.datetime
