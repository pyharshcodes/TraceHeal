import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SandboxRunBase(BaseModel):
    service_name: str
    sandbox_type: str = "PROCESS"
    port: int


class SandboxRunCreate(SandboxRunBase):
    incident_id: str
    hypothesis_id: Optional[str] = None


class SandboxRunRead(SandboxRunBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    hypothesis_id: Optional[str] = None
    status: str
    exit_code: Optional[int] = None
    stdout_log: Optional[str] = None
    stderr_log: Optional[str] = None
    reproduction_verified: bool
    reproduction_signature: Optional[str] = None
    created_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
