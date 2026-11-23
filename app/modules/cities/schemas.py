from pydantic import BaseModel, ConfigDict, Field

Name = Field(min_length=1, max_length=100)


class CityCreate(BaseModel):
    name_ru: str = Name
    name_tk: str = Name
    is_active: bool = True


class CityUpdate(BaseModel):
    name_ru: str | None = Field(default=None, min_length=1, max_length=100)
    name_tk: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class CityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_ru: str
    name_tk: str
    is_active: bool
