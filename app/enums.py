from enum import StrEnum


class UserRole(StrEnum):
    user = "user"
    seller = "seller"
    admin = "admin"


class Language(StrEnum):
    ru = "ru"
    tk = "tk"


class ModerationStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
