from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.common import PatchModel
from app.enums import Language, UserRole
from app.phone import normalize_phone

Phone = Annotated[str, AfterValidator(normalize_phone)]


class OtpRequest(BaseModel):
    phone: Phone


class OtpVerify(BaseModel):
    phone: Phone
    code: str = Field(pattern=r"^\d{4,6}$")


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str | None
    role: UserRole
    language: Language
    notify_favorite_shops: bool
    notify_my_malls: bool


class UserUpdate(PatchModel):
    model_config = ConfigDict(extra="forbid")
    non_nullable = frozenset({"language", "notify_favorite_shops", "notify_my_malls"})

    name: str | None = Field(default=None, max_length=100)
    language: Language | None = None
    notify_favorite_shops: bool | None = None
    notify_my_malls: bool | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthOut(TokenPair):
    user: UserOut
