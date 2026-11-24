import pytest

from app.common import PatchModel


def test_non_nullable_must_name_existing_fields():
    with pytest.raises(TypeError, match="nmae"):

        class Broken(PatchModel):
            non_nullable = frozenset({"nmae"})

            name: str | None = None
