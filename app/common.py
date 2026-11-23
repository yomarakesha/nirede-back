"""Schemas shared across modules."""

from pydantic import BaseModel, computed_field

from app.storage import media_url


class PhotoOut(BaseModel):
    path: str

    @computed_field
    @property
    def url(self) -> str:
        return media_url(self.path) or ""


class PhotosIn(BaseModel):
    paths: list[str]
