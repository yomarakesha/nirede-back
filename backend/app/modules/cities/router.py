from fastapi import APIRouter
from sqlalchemy import select

from app.deps import SessionDep
from app.modules.cities.models import City
from app.modules.cities.schemas import CityOut

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get("")
async def list_cities(session: SessionDep) -> list[CityOut]:
    rows = await session.scalars(select(City).where(City.is_active).order_by(City.id))
    return [CityOut.model_validate(c) for c in rows]
