"""Centralized input sanitization + path / content allow-lists.

Used by both the agent side (DB hint sanitization, user message capping)
and the executor side (path validation, string-arg validation before
those values are interpolated into PowerShell scripts).

Design rule: every function here is FAIL-CLOSED. If the input doesn't
match the strict whitelist, we reject — we do NOT try to "clean" it.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

# Zero-width / bidi / format chars that attackers stuff into injection
# markers to slip past ASCII \b word-boundary regex (e.g. "i\u200Bgnore
# previous instructions"). NFKC-normalize first to fold full-width
# letters and ligatures down, then strip these explicitly.
_INVISIBLE_RE = re.compile(
    r"[\u00AD\u034F\u061C\u115F\u1160\u17B4\u17B5"
    r"\u180B-\u180E\u200B-\u200F\u202A-\u202E\u2060-\u2064"
    r"\u2066-\u206F\u3164\uFE00-\uFE0F\uFEFF\uFFA0\uFFF0-\uFFFB]"
)


def _normalize_for_match(s: str) -> str:
    """NFKC-fold + strip invisible / bidi chars so injection regex
    sees the same string the human reads. Also fold ASCII look-alikes
    that bypass plain regex (e.g. zero-width joiner inside a word)."""
    s = unicodedata.normalize("NFKC", s)
    return _INVISIBLE_RE.sub("", s)

# --- Prompt-injection markers we redact from anything that flows back ---
# into the model context (DB hints, persisted problem_summary, etc.).
#
# This is intentionally aggressive — false positives just degrade the
# hint, while a single missed marker can hijack the agent.
# NOTE: Python 3.12+ rejects inline `(?i)` flags anywhere except the start
# of the full pattern. Since we `|`-join these, we must pass the flag to
# re.compile() instead of embedding it.
_INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+"
    r"(instructions?|prompts?|rules?|messages?)\b",
    r"\bsystem\s*(override|prompt|message|:)\b",
    r"\bassistant\s*:",
    r"\byou\s+must\b",
    r"\bnew\s+instruction[s]?\b",
    r"\bjailbreak\b",
    r"\bact\s+as\b",
    r"\bpretend\s+to\s+be\b",
    r"<\s*/?\s*(system|user|assistant|tool|think|tool_call)\s*>",
    r"##\s*(system|instruction|user instruction|tool result)",
    r"\[\s*(system|instruction|inst)\s*[:\]]",
    r"\brun_powershell\b",
    r"\bos\.startfile\b",
    r"\bsubprocess\b",
    r"\bcurl\s+http",
    r"\bwget\s+http",
    r"\biex\b",
    r"\binvoke-expression\b",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# Markdown / role-marker chars that the chat templates use to delimit
# turns. Stripping them out of untrusted text keeps the model from being
# tricked by "##" or backtick-fence injections.
_MARKDOWN_RE = re.compile(r"[`\u2028\u2029]")

# Max length any persisted / re-injected string is allowed to be before
# we truncate. Hint values are concatenated into the next user prompt,
# so we keep them tight.
HINT_MAX_LEN = 200
USER_MSG_MAX_LEN = 2000


def sanitize_for_prompt(text: str, max_len: int = HINT_MAX_LEN) -> str:
    """Make `text` safe to embed inside a user/system prompt.

    - Truncates to `max_len`.
    - Replaces injection markers with [redacted].
    - Strips backticks and Unicode line separators.

    Returns "" for None / empty.
    """
    if not text:
        return ""
    s = str(text)[: max_len * 4]   # bound work up front
    # CRITICAL: normalize FIRST so "i\u200Bgnore" or full-width
    # "Ｉｇｎｏｒｅ" both fold to "ignore" before the regex sees them.
    s = _normalize_for_match(s)
    s = _INJECTION_RE.sub("[redacted]", s)
    s = _MARKDOWN_RE.sub(" ", s)
    s = s.replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len]


def cap_user_message(text: str) -> str:
    """Hard cap + Unicode normalization on the initial user message.
    Prevents both (a) 200 KB document-paste attacks and (b) U+200B /
    bidi-override / full-width tricks that bypass plain ASCII regex
    filters downstream."""
    if not text:
        return ""
    s = str(text)[: USER_MSG_MAX_LEN * 2]
    s = _normalize_for_match(s)
    return s[:USER_MSG_MAX_LEN]


# ----------------------------------------------------------------------
# Executor-side: validate string args BEFORE they touch a PowerShell
# script body. Single-quote injection is the entire attack surface for
# the f-string handlers in client/executor/computer.py.
# ----------------------------------------------------------------------

# Characters we never allow in any arg that's interpolated into PS.
# `'` ends single-quoted strings, `"` ends double-quoted, `` ` `` is the
# PS escape char, `$` triggers variable expansion in double-quoted
# contexts, `;` `&` `|` `\n` chain commands.
_PS_FORBIDDEN_CHARS = "'\"`$;&|\n\r\x00<>()"


def validate_ps_arg(value: str, *, max_len: int = 200, allow_path: bool = False) -> str:
    """Reject any arg that contains shell metacharacters.

    Raises ValueError on rejection. Returns the value unchanged otherwise.
    For path-like args (`allow_path=True`), we allow `:`, `\\`, and `/`.

    Even though we pass these via env vars now (no f-string), we keep
    this as defense in depth.
    """
    if value is None:
        raise ValueError("value is None")
    s = str(value)
    if len(s) > max_len:
        raise ValueError(f"value too long ({len(s)} > {max_len})")
    forbidden = _PS_FORBIDDEN_CHARS
    for ch in forbidden:
        if ch in s:
            raise ValueError(f"forbidden character in value: {ch!r}")
    if not allow_path and ("\\" in s or "/" in s):
        # Plain string fields (clipboard text, query) don't need
        # path separators.
        raise ValueError("path separators not allowed here")
    return s


# ----------------------------------------------------------------------
# File-path allow-list for `read_file_preview` / `search_files`.
# ----------------------------------------------------------------------

def _allowed_roots() -> list[Path]:
    """Directories under which the agent may read files.

    Customize via VOODO_FILE_ALLOWLIST (semicolon-separated). Defaults
    to the user's Documents, Desktop, Downloads + Public.
    """
    raw = os.getenv("VOODO_FILE_ALLOWLIST", "").strip()
    if raw:
        return [Path(p.strip()).resolve() for p in raw.split(";") if p.strip()]
    home = Path.home()
    return [
        (home / "Documents").resolve(),
        (home / "Desktop").resolve(),
        (home / "Downloads").resolve(),
        Path("C:/Users/Public").resolve(),
    ]


def validate_file_path(path: str) -> Path:
    """Resolve `path`, refuse if it escapes the allow-list or contains UNC
    / env-var expansion. Returns the resolved Path on success; raises
    ValueError on rejection."""
    if not path:
        raise ValueError("empty path")
    s = str(path).strip()
    if len(s) > 400:
        raise ValueError("path too long")
    # Block UNC, env expansion, and obviously-bad chars.
    if s.startswith("\\\\") or s.startswith("//"):
        raise ValueError("UNC paths not allowed")
    if "%" in s or "$env:" in s.lower() or "$" in s:
        raise ValueError("variable expansion not allowed in paths")
    for ch in "`;&|<>\"'\n\r\x00":
        if ch in s:
            raise ValueError(f"forbidden char in path: {ch!r}")
    try:
        p = Path(s).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        raise ValueError(f"cannot resolve path: {e}") from e
    roots = _allowed_roots()
    for root in roots:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise ValueError(
        f"path '{p}' is outside the voodo allow-list "
        f"({', '.join(str(r) for r in roots)})"
    )
