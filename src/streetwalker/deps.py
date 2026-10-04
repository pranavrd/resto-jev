"""Request-scoped database connection shared by the API routers. Tests override `get_conn` to roll back."""

from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends
from psycopg.rows import dict_row

from streetwalker import db


def get_conn() -> Iterator[psycopg.Connection]:
    with db.connect() as conn:  # commits on a clean exit, rolls back on an exception
        conn.row_factory = dict_row
        yield conn


Conn = Annotated[psycopg.Connection, Depends(get_conn)]
