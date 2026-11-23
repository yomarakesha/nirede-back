"""Import every module's models so Base.metadata is complete (Alembic, tests)."""

from app.modules.categories import models as categories  # noqa: F401
from app.modules.cities import models as cities  # noqa: F401
from app.modules.malls import models as malls  # noqa: F401
from app.modules.shops import models as shops  # noqa: F401
from app.modules.users import models as users  # noqa: F401
