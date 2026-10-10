from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class FeedbackSection(BaseModel):
    section_name: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    suggestions: list[str]


class ReviewCreate(BaseModel):
    profile_id: UUID


class WebhookRegister(BaseModel):
    callback_url: HttpUrl


class ReviewResponse(BaseModel):
    id: UUID
    profile_id: UUID
    status: str
    sections: list[FeedbackSection] | None
    overall_score: float | None
    error_message: str | None = None
    callback_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    page: int
    page_size: int
