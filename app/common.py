"""Schemas shared across modules."""

from typing import ClassVar

from pydantic import BaseModel, computed_field, model_validator

from app.storage import media_url


class PhotoOut(BaseModel):
    path: str

    @computed_field
    @property
    def url(self) -> str:
        return media_url(self.path) or ""


class PhotosIn(BaseModel):
    paths: list[str]


class PatchModel(BaseModel):
    """Partial update: omitted fields stay as they are; `null` is allowed only for nullable ones."""

    non_nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_nulls(self):
        bad = sorted(
            f for f in self.model_fields_set if f in self.non_nullable and getattr(self, f) is None
        )
        if bad:
            raise ValueError(f"null is not allowed for: {', '.join(bad)}")
        return self
