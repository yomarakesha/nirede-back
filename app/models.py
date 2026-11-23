"""Import every module's models so Base.metadata is complete (Alembic, tests)."""

from app.modules.users import models as users  # noqa: F401
