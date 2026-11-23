from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.enums import ModerationStatus
from app.modules.moderation.models import EntityType


class ChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: EntityType
    entity_id: int
    author_id: int
    payload: dict[str, Any]
    status: ModerationStatus
    admin_comment: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ChangeRequestAdminOut(ChangeRequestOut):
    current: dict[str, Any] | None
