from pydantic import BaseModel

class KeyValueRequest(BaseModel):
    key: str
    value: str

class MessageResponse(BaseModel):
    message: str
    key: str
    value: str
    
class JobRequest(BaseModel):
    key: str
    value: str
    
class JobQueuedResponse(BaseModel):
    message: str
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    key: str | None = None
    value: str | None = None