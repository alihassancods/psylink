"""Splitting a SQL script into individual statements.

asyncpg sends every statement as a prepared statement, which refuses more than one command at a
time, so a `.sql` migration has to be cut up before it can be applied. Cutting on every `;`
would shred the `do $$ ... $$;` blocks and function bodies in these files, so this walks the
script and only breaks on a semicolon that sits in plain SQL — outside a string, quoted
identifier, dollar-quoted body, or comment.

Used by the alembic revision that applies supabase/migrations; Supabase's own `db push` runs the
same files as scripts and needs no splitting.
"""

import re

_DOLLAR_TAG = re.compile(r"\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*)?\$")


def _end_of_quote(script: str, start: int, closer: str) -> int:
    """Index just past the quoted run beginning at `start`.

    For a single quote, `''` is an escaped quote rather than the end; double-quoted identifiers
    have no such doubling.
    """
    index = start + 1
    while index < len(script):
        if script[index] == closer:
            if closer == "'" and script[index + 1 : index + 2] == "'":
                index += 2
                continue
            return index + 1
        index += 1
    return len(script)


def _end_of_block_comment(script: str, start: int) -> int:
    """Index just past a `/* ... */`, which Postgres allows to nest."""
    index = start + 2
    depth = 1
    while index < len(script) and depth:
        if script.startswith("/*", index):
            depth += 1
            index += 2
        elif script.startswith("*/", index):
            depth -= 1
            index += 2
        else:
            index += 1
    return index


def split_sql_statements(script: str) -> list[str]:
    """Return the statements in `script`, in order, without their trailing semicolons.

    Comments and whitespace stay attached to the statement they precede. Empty statements are
    dropped, so `select 1;;;` yields one entry. An unterminated quote or dollar-quote runs to the
    end of the input rather than raising.
    """
    statements: list[str] = []
    length = len(script)
    start = 0
    index = 0

    while index < length:
        char = script[index]

        if char == ";":
            _append(statements, script[start:index])
            index += 1
            start = index
            continue

        # -- line comment: everything up to the newline is inert
        if char == "-" and script[index + 1 : index + 2] == "-":
            end = script.find("\n", index)
            index = length if end == -1 else end
            continue

        # /* block comment */, possibly nested
        if char == "/" and script[index + 1 : index + 2] == "*":
            index = _end_of_block_comment(script, index)
            continue

        # 'string literal' / "quoted identifier": a semicolon inside means nothing
        if char in ("'", '"'):
            index = _end_of_quote(script, index, char)
            continue

        # $tag$body$tag$: a function or DO body, semicolons and all
        if char == "$":
            quote = _DOLLAR_TAG.match(script, index)
            if quote is not None:
                marker = quote.group(0)
                end = script.find(marker, index + len(marker))
                index = length if end == -1 else end + len(marker)
                continue

        index += 1

    _append(statements, script[start:])

    return statements


def _append(statements: list[str], piece: str) -> None:
    statement = piece.strip()
    if statement:
        statements.append(statement)
