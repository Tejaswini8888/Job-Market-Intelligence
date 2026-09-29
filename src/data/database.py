"""PostgreSQL connection layer for the Job Market Intelligence platform.

This module is the ONLY place in the project that knows how to reach
PostgreSQL. Everything else (query functions, tests, future dashboards)
imports from here.

What it does
------------
1. Loads connection settings from the ``.env`` file with ``python-dotenv``.
2. Builds a psycopg 3 connection from those settings.
3. Fails with a clear, password-free error message.
4. Runs SQL and hands the result back as a ``pandas.DataFrame``.

Security rules that are baked into this file
--------------------------------------------
* The password is read from the environment only. It is never written to
  disk, printed, logged, or embedded in an error message.
* The password is passed to psycopg as a keyword argument, so it never
  becomes part of a printable connection string.
* Every message produced here is passed through :func:`_scrub`, which
  replaces the password with ``***`` if a driver message ever echoed it.
* Connections are read-only by default (``DEFAULT_READ_ONLY``), so this
  data-access layer cannot modify the database by accident.

Usage
-----
Run from the project root::

    python src/data/database.py        # prints a safe connection report

    from src.data.database import fetch_dataframe
    df = fetch_dataframe("SELECT * FROM jobs ORDER BY posted_date DESC")

    from src.data.queries import get_all_jobs
    df = get_all_jobs()
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg import Connection
from psycopg.rows import dict_row

# src/data/database.py -> src/data -> src -> project root
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
ENV_FILE: Path = PROJECT_ROOT / ".env"

# Real environment variables always win over the values in .env, so CI or a
# shell session can override the file without editing it.
load_dotenv(dotenv_path=ENV_FILE)

#: Variables that must be present for a connection to be possible.
REQUIRED_ENV_VARS: tuple[str, ...] = (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
)

#: Seconds to wait for the TCP connection before giving up. A short timeout
#: turns "server is not running" into a fast error instead of a long hang.
DEFAULT_CONNECT_TIMEOUT: int = 5

#: Read-only sessions. This stage only ever SELECTs, so writes are blocked
#: at the database level. Set to False only if a future stage needs to write.
DEFAULT_READ_ONLY: bool = True

#: Server option that makes every statement in the session read-only.
READ_ONLY_OPTION: str = "-c default_transaction_read_only=on"


class ConfigurationError(RuntimeError):
    """Raised when the database settings are missing or unusable."""


class DatabaseConnectionError(RuntimeError):
    """Raised when PostgreSQL cannot be reached or refuses the connection."""


def _scrub(message: str, password: str) -> str:
    """Return ``message`` with ``password`` replaced by ``***``.

    psycopg error messages never contain the password, but this guard makes
    that guarantee unconditional: even a surprising driver message cannot
    leak the secret into a terminal, log file, or pytest report.
    """
    if password:
        return message.replace(password, "***")
    return message


def get_database_config() -> dict[str, Any]:
    """Read the database settings from the environment.

    :returns: ``{"DB_HOST": ..., "DB_PORT": int, "DB_NAME": ...,
        "DB_USER": ..., "DB_PASSWORD": ...}``
    :raises ConfigurationError: if a variable is missing, blank, or
        ``DB_PORT`` is not a whole number.

    The returned password must never be printed or logged by calling code.
    """
    config: dict[str, Any] = {}
    missing: list[str] = []

    for name in REQUIRED_ENV_VARS:
        raw_value = os.getenv(name)
        if raw_value is None or not raw_value.strip():
            missing.append(name)
        else:
            config[name] = raw_value.strip()

    if missing:
        raise ConfigurationError(
            "Missing database setting(s): "
            + ", ".join(missing)
            + f". Copy .env.example to {ENV_FILE.name} in the project root "
            "and fill in the values (including DB_PASSWORD)."
        )

    try:
        config["DB_PORT"] = int(config["DB_PORT"])
    except ValueError as exc:
        raise ConfigurationError(
            f"DB_PORT must be a whole number, got {config['DB_PORT']!r}."
        ) from exc

    return config


def describe_database_target() -> dict[str, Any]:
    """Describe where the code is trying to connect, without the password.

    Safe to print: it reports only whether a password is configured, never
    the password itself.
    """
    try:
        config = get_database_config()
    except ConfigurationError as exc:
        return {
            "configured": False,
            "env_file": str(ENV_FILE),
            "env_file_found": ENV_FILE.exists(),
            "problem": str(exc),
        }

    return {
        "configured": True,
        "host": config["DB_HOST"],
        "port": config["DB_PORT"],
        "database": config["DB_NAME"],
        "user": config["DB_USER"],
        "password_configured": True,  # never the password itself
        "read_only": DEFAULT_READ_ONLY,
        "env_file": str(ENV_FILE),
        "env_file_found": ENV_FILE.exists(),
    }


def get_connection(
    *,
    autocommit: bool = True,
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
    read_only: bool = DEFAULT_READ_ONLY,
) -> Connection[Any]:
    """Open a new PostgreSQL connection using the environment settings.

    :param autocommit: if ``True`` each statement commits on its own, which
        is what read-only analytics needs.
    :param connect_timeout: seconds to wait for the connection to be accepted.
    :param read_only: if ``True`` the session runs with writes disabled.
    :returns: an open :class:`psycopg.Connection`.
    :raises ConfigurationError: if the settings are missing or invalid.
    :raises DatabaseConnectionError: if the server cannot be reached or the
        credentials are refused. The message never contains the password.

    The caller owns the connection and must close it (or use
    :func:`connection_scope`, which closes it automatically).
    """
    config = get_database_config()
    password = str(config["DB_PASSWORD"])

    try:
        return psycopg.connect(
            host=config["DB_HOST"],
            port=config["DB_PORT"],
            dbname=config["DB_NAME"],
            user=config["DB_USER"],
            password=password,
            connect_timeout=connect_timeout,
            autocommit=autocommit,
            row_factory=dict_row,
            options=READ_ONLY_OPTION if read_only else None,
        )
    except psycopg.Error as exc:
        detail = _scrub(str(exc).strip(), password)
        raise DatabaseConnectionError(
            "Could not connect to PostgreSQL at "
            f"{config['DB_HOST']}:{config['DB_PORT']} "
            f"(database '{config['DB_NAME']}', user '{config['DB_USER']}'). "
            "Check that the PostgreSQL service is running and that "
            f"{ENV_FILE.name} holds the correct DB_USER / DB_PASSWORD. "
            f"Driver message: {detail}"
        ) from None


@contextmanager
def connection_scope(
    *,
    autocommit: bool = True,
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
    read_only: bool = DEFAULT_READ_ONLY,
) -> Iterator[Connection[Any]]:
    """Yield a connection and close it again, even if the body raises.

    Example::

        with connection_scope() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                value = cursor.fetchone()
    """
    connection = get_connection(
        autocommit=autocommit,
        connect_timeout=connect_timeout,
        read_only=read_only,
    )
    try:
        yield connection
    finally:
        connection.close()


def fetch_dataframe(
    sql: str,
    params: Sequence[Any] | dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Run a single SELECT and return the rows as a ``pandas.DataFrame``.

    :param sql: one SQL statement. Values must be passed as ``params`` with
        psycopg placeholders (``%s`` positional, ``%(name)s`` named) - never
        by pasting them into the string.
    :param params: the values for those placeholders.
    :returns: a DataFrame whose columns follow the SELECT list. An empty
        result still returns a DataFrame with the correct columns, never
        ``None``.
    :raises ValueError: if ``sql`` is empty.
    :raises DatabaseConnectionError: if the database is unreachable.
    :raises psycopg.Error: if PostgreSQL rejects the statement.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("sql must be a non-empty string.")

    with connection_scope() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            # cursor.description is None for statements that return no rows.
            columns: list[str] = [column.name for column in cursor.description or []]

    if not rows:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(rows, columns=columns)


def test_connection() -> dict[str, Any]:
    """Open a connection, confirm it works, and return a safe status summary.

    :returns: ``{"connected": True, "database": ..., "user": ...,
        "server_version": ...}``
    :raises DatabaseConnectionError: if the connection or the test query fails.
    """
    config = get_database_config()

    with connection_scope() as connection:
        with connection.cursor() as cursor:
            # Every expression is aliased: without AS, two current_setting()
            # calls would both be named "current_setting" and the second one
            # would silently overwrite the first in the result row.
            cursor.execute(
                "SELECT current_database()          AS current_database, "
                "       current_user               AS current_user, "
                "       current_setting('server_version') "
                "                                   AS server_version, "
                "       current_setting('default_transaction_read_only') "
                "                                   AS read_only"
            )
            row = cursor.fetchone() or {}

    return {
        "connected": True,
        "host": config["DB_HOST"],
        "port": config["DB_PORT"],
        "database": row.get("current_database"),
        "user": row.get("current_user"),
        "server_version": row.get("server_version"),
        "read_only": row.get("read_only"),
    }


def main() -> None:
    """Print a password-free connection report. Used for manual validation."""
    print("PostgreSQL connection report")
    print("-" * 60)
    for key, value in describe_database_target().items():
        print(f"{key:>18}: {value}")

    print("-" * 60)
    try:
        result = test_connection()
    except (ConfigurationError, DatabaseConnectionError) as exc:
        print(f"{'status':>18}: FAILED\n{'error':>18}: {exc}")
        return

    for key, value in result.items():
        print(f"{key:>18}: {value}")

    table_names = ("companies", "jobs", "skills", "job_skills")
    print("-" * 60)
    print(f"{'table':>18}: rows")
    for table_name in table_names:
        # Table names come from the constant above, never from user input.
        frame = fetch_dataframe(f"SELECT COUNT(*) AS row_count FROM {table_name}")
        print(f"{table_name:>18}: {int(frame['row_count'].iloc[0])}")

    print("-" * 60)
    print(f"{'status':>18}: OK")


if __name__ == "__main__":
    main()
