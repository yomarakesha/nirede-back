from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_or_404
from app.modules.cities.models import City


async def get_city_or_404(session: AsyncSession, city_id: int) -> City:
    return await get_or_404(session, City, city_id, "city_not_found")
