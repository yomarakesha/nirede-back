from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.enums import ModerationStatus
from app.modules.shops.schemas import ShopBrief, ShopCreate
from app.modules.users.schemas import Phone


class ApplicationIn(BaseModel):
    shop_id: int | None = None
    shop_name: str = Field(min_length=1, max_length=100)
    mall_id: int | None = None
    floor: int | None = Field(default=None, ge=0, le=500)
    row: str | None = Field(default=None, max_length=16)
    number: str | None = Field(default=None, max_length=16)
    city_id: int | None = None
    address: str | None = Field(default=None, max_length=255)
    contact_phone: Phone


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    shop_id: int | None
    shop_name: str
    mall_id: int | None
    floor: int | None
    row: str | None
    number: str | None
    city_id: int | None
    address: str | None
    contact_phone: str
    status: ModerationStatus
    admin_comment: str | None
    reviewed_at: datetime | None
    created_at: datetime


class SubscriptionIn(BaseModel):
    amount: Decimal = Field(default=Decimal("30"), ge=0, max_digits=10, decimal_places=2)
    days: int = Field(default=30, ge=1, le=366)
    note: str | None = Field(default=None, max_length=500)


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_id: int
    starts_at: datetime
    ends_at: datetime
    amount: Decimal
    activated_by: int | None
    note: str | None


class ApproveIn(BaseModel):
    shop: ShopCreate | None = None
    subscription: SubscriptionIn | None = None


class SellerShopOut(ShopBrief):
    subscription_ends_at: datetime | None
    pending_change_requests: int
