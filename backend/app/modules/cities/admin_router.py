from fastapi import APIRouter, status
from sqlalchemy import select

from app.crud import apply_update, delete_or_409, paginate
from app.deps import AdminUser, SessionDep
from app.modules.cities.models import City
from app.modules.cities.schemas import CityCreate, CityOut, CityUpdate
from app.modules.cities.service import get_city_or_404
from app.pagination import Page, PageDep

router = APIRouter(prefix="/admin/cities", tags=["admin: cities"])


@router.get("")
async def list_cities(_: AdminUser, session: SessionDep, page: PageDep) -> Page[CityOut]:
    items, total = await paginate(session, select(City).order_by(City.id), page)
    return Page(items=[CityOut.model_validate(c) for c in items], total=total)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_city(body: CityCreate, _: AdminUser, session: SessionDep) -> CityOut:
    city = City(**body.model_dump())
    session.add(city)
    await session.commit()
    return CityOut.model_validate(city)


@router.get("/{city_id}")
async def get_city(city_id: int, _: AdminUser, session: SessionDep) -> CityOut:
    return CityOut.model_validate(await get_city_or_404(session, city_id))


@router.patch("/{city_id}")
async def update_city(city_id: int, body: CityUpdate, _: AdminUser, session: SessionDep) -> CityOut:
    city = await get_city_or_404(session, city_id)
    apply_update(city, body)
    await session.commit()
    return CityOut.model_validate(city)


@router.delete("/{city_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_city(city_id: int, _: AdminUser, session: SessionDep) -> None:
    await delete_or_409(session, await get_city_or_404(session, city_id), "city_in_use")
