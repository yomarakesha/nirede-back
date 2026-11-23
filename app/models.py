"""Import every module's models so Base.metadata is complete (Alembic, tests)."""

from app.modules.users import models as users  # noqa: F401
from app.modules.cities import models as cities  # noqa: F401
