"""CSV preparation and restricted, read-only business analytics queries."""
from __future__ import annotations

import io
import json
import re
import sqlite3
import time
from typing import Any

import pandas as pd

MAX_CSV_BYTES = 20 * 1024 * 1024
MAX_RESULT_ROWS = 101
SQLITE_FUNCTIONS = {
    "abs", "avg", "cast", "char", "coalesce", "count", "cume_dist", "date",
    "datetime", "dense_rank", "first_value", "group_concat", "hex", "ifnull",
    "instr", "julianday", "lag", "last_value", "lead", "length", "like",
    "likelihood", "lower", "ltrim", "max", "min", "nullif", "ntile", "percent_rank",
    "power", "printf", "quote", "rank", "replace", "round", "row_number",
    "rtrim", "sign", "sqrt", "strftime", "substr", "substring", "sum", "time",
    "total", "trim", "typeof", "unicode", "unixepoch", "upper",
}


def _deduplicate_column_names(columns: list[str]) -> list[str]:
    used: set[str] = set()
    result: list[str] = []
    for i, raw in enumerate(columns, 1):
        base = str(raw).strip() or f"column_{i}"
        name = base
        suffix = 2
        while name.casefold() in used:
            name = f"{base}_{suffix}"
            suffix += 1
        result.append(name)
        used.add(name.casefold())
    return result


def load_csv(blob: bytes, delimiter: str = "Auto detect") -> pd.DataFrame:
    if not blob:
        raise ValueError("The file is empty.")
    if len(blob) > MAX_CSV_BYTES:
        raise ValueError("File is too large (20 MB maximum for this starter version).")
    seps = {"Comma": ",", "Semicolon": ";", "Tab": "\t", "Pipe": "|"}
    if delimiter != "Auto detect" and delimiter not in seps:
        raise ValueError("Unsupported delimiter.")
    sep = seps.get(delimiter)
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            if sep is None:
                df = pd.read_csv(io.BytesIO(blob), encoding=encoding, sep=None,
                                 engine="python", on_bad_lines="error")
            else:
                df = pd.read_csv(io.BytesIO(blob), encoding=encoding, sep=sep,
                                 low_memory=False, on_bad_lines="error")
            break
        except (UnicodeError, pd.errors.ParserError) as exc:
            last_error = exc
    else:
        raise ValueError(f"CSV could not be parsed: {last_error}") from last_error
    if df.empty or not len(df.columns):
        raise ValueError("Your CSV needs a header and at least one data row.")
    df.columns = _deduplicate_column_names([str(c) for c in df.columns])
    # Parse likely date columns but do not automatically convert ID/year columns.
    for c in df.columns:
        if pd.api.types.is_object_dtype(df[c]) and re.search(
            r"date|timestamp|created_at|updated_at|ordered_at|shipped_at", c, re.I
        ):
            try:
                converted = pd.to_datetime(df[c], errors="coerce")
                nonnull = df[c].notna().sum()
                if nonnull and converted.notna().sum() / nonnull >= 0.85:
                    df[c] = converted
            except (ValueError, TypeError, OverflowError):
                pass
    return df


def describe_schema(df: pd.DataFrame) -> str:
    items: list[dict[str, Any]] = []
    for name in df.columns:
        s = df[name]
        if pd.api.types.is_datetime64_any_dtype(s):
            kind = "date (ISO timestamp text in SQLite)"
        elif pd.api.types.is_numeric_dtype(s):
            kind = "number"
        else:
            kind = "text/category"
        items.append({"name": name, "type": kind, "missing_values": int(s.isna().sum())})
    return json.dumps({"table": "data", "rows": len(df), "columns": items}, ensure_ascii=False)


def _to_sqlite_types(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    for name in prepared.columns:
        series = prepared[name]
        if pd.api.types.is_datetime64_any_dtype(series):
            prepared[name] = series.dt.strftime("%Y-%m-%d %H:%M:%S")
        elif pd.api.types.is_bool_dtype(series):
            prepared[name] = series.astype("Int64")
    return prepared


def _check_read_only(statement: str) -> str:
    sql = statement.strip()
    if not re.match(r"^(select|with)\b", sql, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if ";" in sql.rstrip("; \n\t"):
        raise ValueError("Multiple SQL statements are not allowed.")
    return sql.rstrip("; \n\t")


def run_readonly_query(df: pd.DataFrame, statement: str, timeout_seconds: int = 6) -> pd.DataFrame:
    """Read from only an in-memory, single-table SQLite DB; deny all mutations.

    SQLite's native authorizer checks operations after parsing SQL. A progress
    handler interrupts heavy queries. The preview is capped at 100 rows.
    """
    sql = _check_read_only(statement)
    conn = sqlite3.connect(":memory:")
    try:
        conn.enable_load_extension(False)
        _to_sqlite_types(df).to_sql("data", conn, if_exists="replace", index=False)
        def authorize(op: int, arg1: str | None, arg2: str | None,
                      db: str | None, source: str | None) -> int:
            if op == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if op == sqlite3.SQLITE_READ:
                # No metadata tables; otherwise only the uploaded in-memory DB.
                if db not in ("main", None) or (arg1 or "").lower().startswith("sqlite_"):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            if op == sqlite3.SQLITE_FUNCTION:
                return (sqlite3.SQLITE_OK if (arg2 or arg1 or "").lower()
                        in SQLITE_FUNCTIONS else sqlite3.SQLITE_DENY)
            return sqlite3.SQLITE_DENY
        conn.set_authorizer(authorize)
        started = time.monotonic()
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() - started > timeout_seconds else 0, 10_000
        )
        cur = conn.execute(sql)
        if not cur.description:
            raise ValueError("The query did not return a result table.")
        records = cur.fetchmany(MAX_RESULT_ROWS)
        if len(records) > 100:
            records = records[:100]
        result = pd.DataFrame(records, columns=[x[0] for x in cur.description])
        return result
    except sqlite3.Error as exc:
        raise ValueError(f"The query could not be completed safely: {exc}") from exc
    finally:
        conn.close()


def suggestion_questions(df: pd.DataFrame) -> list[str]:
    numbers = [x for x in df.columns if pd.api.types.is_numeric_dtype(df[x])]
    groups = [x for x in df.columns if not pd.api.types.is_numeric_dtype(df[x])
              and not pd.api.types.is_datetime64_any_dtype(df[x])]
    dates = [x for x in df.columns if pd.api.types.is_datetime64_any_dtype(df[x])]
    ideas = ["How many records are in this dataset?"]
    if numbers:
        ideas.append(f"What is the total {numbers[0]}?")
    if groups and numbers:
        ideas.append(f"Which {groups[0]} has the highest total {numbers[0]}?")
    elif groups:
        ideas.append(f"How many records are there for each {groups[0]}?")
    if dates and numbers:
        ideas.append(f"Show monthly trend of total {numbers[0]} using {dates[0]}.")
    return ideas
