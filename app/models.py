import json
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, field_validator


class AccountCreate(BaseModel):
    username: str
    session_json: str
    proxy: Optional[str] = None

    @field_validator("session_json")
    @classmethod
    def validate_session_json(cls, v: str) -> str:
        try:
            json.loads(v)
        except Exception as e:
            raise ValueError(f"Invalid JSON string: {e}")
        return v


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    proxy: Optional[str] = None
    status: str
    last_error: Optional[str] = None
    created_at: str


class LikeRequest(BaseModel):
    url: str
    account_id: int


class LikeMyPostRequest(BaseModel):
    url: str
    max_likes: Optional[int] = None


class LikeMyPostResponse(BaseModel):
    url: str
    enqueued: int
    skipped_already_liked: int
    job_ids: List[int]


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    account_id: int
    username: Optional[str] = None
    account_username: Optional[str] = None
    status: str
    result: Optional[str] = None
    attempts: int
    created_at: str
    updated_at: str
