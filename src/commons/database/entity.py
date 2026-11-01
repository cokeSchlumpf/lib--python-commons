from commons.id_operators import new_id
from commons.string_operators import pluralize, to_snake_case
from sqlalchemy.orm import declared_attr
from sqlmodel import Field, SQLModel


def _entity_tablename(class_name: str) -> str:
    """``CountryORM`` -> ``countries`` (strip the ORM suffix, snake-case, pluralise)."""
    return pluralize(to_snake_case(class_name.removesuffix("ORM")))


class EntityMixin(SQLModel):
    """Base for an operational entity table: a generated ``id`` primary key and a derived table name.

    Inheriting it (with ``table=True``) gives the table a UUIDv7-string ``id`` PK (`commons.id_operators.new_id`) and a name derived from
    the class (``CountryORM`` -> ``countries``) via ``declared_attr`` (so it runs at class-creation time).
    Override the name by setting ``__tablename__`` explicitly on the subclass.
    """

    id: str = Field(
        default_factory=new_id,
        primary_key=True,
        min_length=36,
        max_length=36,
    )

    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore  # declared_attr vs SQLModel's __tablename__ class var
        return _entity_tablename(cls.__name__)
