"""Postgres + pgvector client for the shared solutions DB.

Connects to DATABASE_URL (set in .env). pgvector for similarity search,
sentence-transformers for embeddings.
"""
from __future__ import annotations

import functools
import json
from typing import Any

import psycopg
from psycopg.rows import dict_row

from shared.config import settings
from shared.protocol import SolutionMatch, SolutionRecord, SolutionStep, ToolCall
from shared.security import sanitize_for_prompt

# Allowed values for the `type` column in pending_changes. The submit
# endpoint accepts user input here, so we enforce a closed set.
_ALLOWED_CHANGE_TYPES = {"add", "delete"}

# ── Pending change helpers (inline — avoids touching shared/protocol.py) ──────

def submit_pending_change(
    change_type: str,
    problem_summary: str,
    reason: str,
    submitted_by: str = "IT Admin",
    fix_description: str | None = None,
    solution_id: str | None = None,
    steps_json: str | None = None,
) -> dict:
    """Persist a pending change. Whatever lands here will be RENDERED
    in the IT dashboard AND, on approval, embedded + served as a hint
    to future agent runs. Sanitize EVERY text field here regardless of
    who submitted it — IT dashboard, agent self-write, or unknown
    future caller. This is the chokepoint that previously was missing
    on the IT-dashboard side."""
    if change_type not in _ALLOWED_CHANGE_TYPES:
        raise ValueError(f"submit_pending_change: invalid type {change_type!r}")
    safe_problem = sanitize_for_prompt(problem_summary or "", max_len=300)
    safe_fix = sanitize_for_prompt(fix_description or "", max_len=500) if fix_description else None
    safe_reason = sanitize_for_prompt(reason or "", max_len=300)
    safe_submitter = sanitize_for_prompt(submitted_by or "", max_len=64)
    # Steps come in as JSON. Drop any step whose tool isn't on the
    # allow-list — so an attacker-controlled `steps_json` can't write
    # forbidden tools (e.g. a resurrected run_powershell) into the DB.
    safe_steps_json = _sanitize_steps_json(steps_json)
    sql = """
        insert into pending_changes
            (type, solution_id, problem_summary, fix_description, steps, reason, submitted_by)
        values (%s, %s::uuid, %s, %s, %s::jsonb, %s, %s)
        returning id::text, created_at::text
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (
            change_type, solution_id, safe_problem,
            safe_fix, safe_steps_json, safe_reason, safe_submitter,
        ))
        row = cur.fetchone()
        conn.commit()
    return {
        "id": row["id"],
        "type": change_type,
        "solution_id": solution_id,
        "problem_summary": safe_problem,
        "fix_description": safe_fix,
        "reason": safe_reason,
        "submitted_by": safe_submitter,
        "status": "pending",
        "reviewer_note": None,
        "created_at": str(row["created_at"]),
        "reviewed_at": None,
    }


def _sanitize_steps_json(raw: str | None) -> str:
    """Parse the incoming steps JSON, drop any step whose tool isn't
    on the agent's allow-list, sanitize notes, and re-serialize.
    Returns '[]' for None or anything malformed (fail closed)."""
    if not raw:
        return "[]"
    try:
        from server.agent.tools import _ALLOWED_TOOLS as _ALLOWED
    except Exception:  # noqa: BLE001 — circular-safe fallback
        _ALLOWED = set()
    try:
        items = json.loads(raw)
    except Exception:  # noqa: BLE001
        return "[]"
    if not isinstance(items, list):
        return "[]"
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if not isinstance(action, dict):
            continue
        tool_name = action.get("name")
        if not isinstance(tool_name, str) or (
            _ALLOWED and tool_name not in _ALLOWED
        ):
            continue
        note = sanitize_for_prompt(item.get("note") or "", max_len=200) if item.get("note") else None
        # Redact `type(text=...)` content from persisted steps — the
        # text the agent typed for THIS user (passwords, search queries,
        # message bodies, anything sensitive that was on-screen) must
        # never end up in the shared DB for other users to retrieve.
        # See exploit #9.
        safe_args = action.get("args")
        if isinstance(safe_args, dict) and tool_name == "type" and "text" in safe_args:
            safe_args = dict(safe_args)
            safe_args["text"] = "<redacted>"
        out.append({"action": {"name": tool_name, "args": safe_args or {}}, "note": note})
    return json.dumps(out)


def get_pending_changes(status: str | None = None) -> list[dict]:
    if status:
        sql = """
            select id::text, type, solution_id::text, problem_summary, fix_description,
                   reason, submitted_by, status, reviewer_note,
                   created_at::text, reviewed_at::text
            from pending_changes
            where status = %s
            order by created_at desc
        """
        params = (status,)
    else:
        sql = """
            select id::text, type, solution_id::text, problem_summary, fix_description,
                   reason, submitted_by, status, reviewer_note,
                   created_at::text, reviewed_at::text
            from pending_changes
            order by created_at desc
        """
        params = ()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def approve_pending_change(change_id: str, reviewer_note: str | None = None) -> bool:
    sql_get = """
        select type, solution_id::text, problem_summary, fix_description, steps
        from pending_changes
        where id = %s and status = 'pending'
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql_get, (change_id,))
        row = cur.fetchone()
        if not row:
            return False

        if row["type"] == "add":
            # Use stored steps if the agent submitted them; otherwise empty.
            steps_data = row["steps"] if isinstance(row["steps"], list) else json.loads(row["steps"] or "[]")
            steps_json = json.dumps(steps_data)
            cur.execute(
                """
                insert into solutions (problem_summary, steps, success, os, embedding)
                values (%s, %s::jsonb, true, 'windows', %s::vector)
                """,
                (row["problem_summary"], steps_json, _vec_literal(embed(row["problem_summary"]))),
            )
        elif row["type"] == "delete" and row["solution_id"]:
            cur.execute("delete from solutions where id = %s", (row["solution_id"],))

        cur.execute(
            """
            update pending_changes
            set status = 'approved', reviewer_note = %s, reviewed_at = now()
            where id = %s
            """,
            (reviewer_note, change_id),
        )
        conn.commit()
    return True


def cancel_pending_change(change_id: str) -> bool:
    """Allow a user to cancel their own pending (not yet reviewed) request."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "delete from pending_changes where id = %s and status = 'pending'",
            (change_id,),
        )
        affected = cur.rowcount
        conn.commit()
    return affected > 0


def reject_pending_change(change_id: str, reviewer_note: str | None = None) -> bool:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            update pending_changes
            set status = 'rejected', reviewer_note = %s, reviewed_at = now()
            where id = %s and status = 'pending'
            """,
            (reviewer_note, change_id),
        )
        affected = cur.rowcount
        conn.commit()
    return affected > 0


@functools.lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def embed(text: str) -> list[float]:
    vec = _embedder().encode(text, normalize_embeddings=True)
    return [float(x) for x in vec.tolist()]


def _connect() -> psycopg.Connection:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        connect_timeout=5,
    )


def _vec_literal(vec: list[float]) -> str:
    """pgvector accepts the textual form '[v1,v2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def search_similar(description: str, top_k: int = 3) -> list[SolutionMatch]:
    """Vector similarity search via cosine distance (`<=>`)."""
    q = embed(description)
    sql = """
        select id::text as id, problem_summary, steps, success, os,
               1 - (embedding <=> %s::vector) as score
        from solutions
        where embedding is not null
        order by embedding <=> %s::vector
        limit %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (_vec_literal(q), _vec_literal(q), top_k))
        rows: list[dict[str, Any]] = cur.fetchall()

    out: list[SolutionMatch] = []
    for row in rows:
        steps_data = row["steps"] if isinstance(row["steps"], list) else json.loads(row["steps"] or "[]")
        steps = [SolutionStep(action=ToolCall(**s["action"]), note=s.get("note"))
                 for s in steps_data]
        out.append(SolutionMatch(
            record=SolutionRecord(
                id=row["id"],
                problem_summary=row["problem_summary"],
                steps=steps,
                success=row["success"],
                os=row["os"],
            ),
            score=float(row["score"]),
        ))
    return out


def record_solution(record: SolutionRecord) -> SolutionRecord:
    """Insert a new solution; embeds problem_summary."""
    steps_json = json.dumps([
        {"action": s.action.model_dump(), "note": s.note}
        for s in record.steps
    ])
    sql = """
        insert into solutions (problem_summary, steps, success, os, embedding)
        values (%s, %s::jsonb, %s, %s, %s::vector)
        returning id::text as id
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (
            record.problem_summary,
            steps_json,
            record.success,
            record.os,
            _vec_literal(embed(record.problem_summary)),
        ))
        new_id = cur.fetchone()["id"]
        conn.commit()
    return record.model_copy(update={"id": new_id})


def get_solution(solution_id: str) -> SolutionRecord | None:
    sql = "select id::text as id, problem_summary, steps, success, os from solutions where id = %s"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (solution_id,))
        row = cur.fetchone()
    if not row:
        return None
    steps_data = row["steps"] if isinstance(row["steps"], list) else json.loads(row["steps"])
    steps = [SolutionStep(action=ToolCall(**s["action"]), note=s.get("note"))
             for s in steps_data]
    return SolutionRecord(
        id=row["id"],
        problem_summary=row["problem_summary"],
        steps=steps,
        success=row["success"],
        os=row["os"],
    )


def save_feedback(rating: str, success: bool | None, summary: str | None,
                  source: str = "browser") -> bool:
    """Record an end-of-run 👍/👎 from the user. Self-heals the table
    on a fresh DB. Returns True on success, False if DB is unreachable."""
    if rating not in ("like", "dislike"):
        return False
    sql_insert = (
        "insert into feedback (rating, success, summary, source) "
        "values (%s, %s, %s, %s)"
    )
    sql_create = (
        "create table if not exists feedback ("
        "id uuid primary key default gen_random_uuid(),"
        "rating text not null check (rating in ('like','dislike')),"
        "success boolean, summary text,"
        "source text not null default 'browser',"
        "created_at timestamptz not null default now())"
    )
    try:
        with _connect() as conn, conn.cursor() as cur:
            try:
                cur.execute(sql_insert, (rating, success, (summary or "")[:2000], source))
            except psycopg.Error:
                conn.rollback()
                cur.execute(sql_create)
                cur.execute(sql_insert, (rating, success, (summary or "")[:2000], source))
            conn.commit()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[db] save_feedback failed: {e}", flush=True)
        return False


_OPEN_APP_ALIASES_DEFAULT: dict[str, str] = {
    "powerpoint":         "powerpnt",
    "word":               "winword",
    "edge":               "msedge",
    "vscode":             "code",
    "calculator":         "calc",
    # Visual Studio 2019/2022 — the actual exe is devenv.exe.
    "visualstudio":       "devenv",
    "visual studio":      "devenv",
    "visual studio 2022": "devenv",
    "visual studio 2019": "devenv",
    "vs":                 "devenv",
    "vs2022":             "devenv",
}


def get_open_app_aliases() -> dict[str, str]:
    """Friendly-name → canonical exe basename map for `open_app`.

    Stored in Postgres (`open_app_aliases` table). On a brand-new DB or
    when the table is missing, the call self-heals by creating + seeding
    it. If the DB is unreachable we fall back to the in-memory defaults
    so a dead Postgres doesn't break basic app launching.
    """
    sql_select = "select alias, canonical from open_app_aliases"
    sql_create = (
        "create table if not exists open_app_aliases ("
        "alias text primary key, canonical text not null)"
    )
    sql_seed = (
        "insert into open_app_aliases (alias, canonical) values (%s, %s) "
        "on conflict (alias) do nothing"
    )
    try:
        with _connect() as conn, conn.cursor() as cur:
            try:
                cur.execute(sql_select)
                rows = cur.fetchall()
            except psycopg.Error:
                # Table missing — create and seed defaults, then re-query.
                conn.rollback()
                cur.execute(sql_create)
                for k, v in _OPEN_APP_ALIASES_DEFAULT.items():
                    cur.execute(sql_seed, (k, v))
                conn.commit()
                cur.execute(sql_select)
                rows = cur.fetchall()
        return {r["alias"]: r["canonical"] for r in rows}
    except Exception:  # noqa: BLE001
        return dict(_OPEN_APP_ALIASES_DEFAULT)


def get_all_solutions(limit: int = 100) -> list[SolutionRecord]:
    """List recent solutions. Defensive against bad rows: a row whose
    `steps` JSON is malformed, or references a tool name that's no
    longer in the `ToolName` Literal (after a protocol bump), used to
    crash the whole endpoint with a generic 500. Now we skip the bad
    row, log WHY it was dropped, and keep going so the dashboard still
    renders the healthy ones."""
    import logging
    log = logging.getLogger("voodo.db")

    sql = "select id::text as id, problem_summary, steps, success, os from solutions order by created_at desc limit %s"
    out: list[SolutionRecord] = []
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (limit,))
        rows = cur.fetchall()

    skipped = 0
    for row in rows:
        try:
            raw_steps = row.get("steps")
            if raw_steps is None:
                steps_data = []
            elif isinstance(raw_steps, list):
                steps_data = raw_steps
            else:
                steps_data = json.loads(raw_steps)

            steps: list[SolutionStep] = []
            for s in steps_data:
                if not isinstance(s, dict) or not isinstance(s.get("action"), dict):
                    continue
                try:
                    steps.append(SolutionStep(
                        action=ToolCall(**s["action"]),
                        note=s.get("note"),
                    ))
                except Exception as step_err:  # noqa: BLE001
                    # Most common cause: row references a tool name that
                    # was removed from shared/protocol.py:ToolName since
                    # the row was written. Skip just this step, not the
                    # whole solution.
                    log.warning(
                        "get_all_solutions: skipping step in solution %s (%s)",
                        row.get("id"), step_err,
                    )

            out.append(SolutionRecord(
                id=row["id"],
                problem_summary=row["problem_summary"] or "",
                steps=steps,
                success=bool(row["success"]) if row["success"] is not None else True,
                os=row["os"] or "windows",
            ))
        except Exception as row_err:  # noqa: BLE001
            skipped += 1
            log.warning(
                "get_all_solutions: skipping malformed row %s (%s)",
                row.get("id"), row_err,
            )

    if skipped:
        log.warning("get_all_solutions: skipped %d malformed row(s)", skipped)
    return out

def get_app_instructions(mode: str) -> dict[str, str]:
    """Return all app instructions for the given mode."""
    sql = "SELECT topic, control_instruction, guide_instruction FROM app_instructions"
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            out = {}
            for row in rows:
                inst = row["guide_instruction"] if mode == "guide" else row["control_instruction"]
                if inst:
                    out[row["topic"]] = inst
            return out
    except Exception as e:
        print(f"Error fetching app instructions: {e}")
        return {}
