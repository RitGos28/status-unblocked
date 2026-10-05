"""INSERT ... ON CONFLICT DO NOTHING, for the two databases we run on.

Used where concurrent requests may create the same row: the loser's insert
does nothing instead of raising, and a following SELECT reads the winner's
row. This avoids SAVEPOINT-and-retry, which pysqlite does not support by
default.
"""

from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import Executable


def insert_ignoring_conflict(
    session: Session, model: type[Any], values: dict[str, Any], conflict_columns: list[str]
) -> None:
    dialect = session.get_bind().dialect.name
    statement: Executable
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        statement = (
            pg_insert(model).values(**values).on_conflict_do_nothing(index_elements=conflict_columns)
        )
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        statement = (
            sqlite_insert(model)
            .values(**values)
            .on_conflict_do_nothing(index_elements=conflict_columns)
        )
    else:
        raise RuntimeError(f"insert_ignoring_conflict is not implemented for {dialect!r}")
    session.execute(statement)
