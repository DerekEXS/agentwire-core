"""Redaction engine: shared catalog of sensitive patterns.

Patterns are served via GET /redact/patterns so other tools (CUE plugin
host) can fetch and reuse the same rules. The catalog is hard-coded as
a fallback; in production it can be replaced by an external YAML.

HistoryManager.set_patterns() is called at startup to load these.
"""
import json
import re
from pathlib import Path

# Default catalog — used if no external file is provided.
DEFAULT_PATTERNS: list[dict] = [
    {
        "name": "anthropic_key",
        "regex": r"sk-ant-[a-zA-Z0-9\-_]{20,}",
        "replacement": "[REDACTED:ANTHROPIC_KEY]",
    },
    {
        "name": "openai_key",
        "regex": r"sk-[a-zA-Z0-9]{40,}",
        "replacement": "[REDACTED:OPENAI_KEY]",
    },
    {
        "name": "github_pat",
        "regex": r"ghp_[a-zA-Z0-9]{30,}",
        "replacement": "[REDACTED:GITHUB_PAT]",
    },
    {
        "name": "bearer_token",
        "regex": r"(?i)Bearer\s+[a-zA-Z0-9._\-]{20,}",
        "replacement": "Bearer [REDACTED:TOKEN]",
    },
    {
        "name": "jwt",
        "regex": r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+",
        "replacement": "[REDACTED:JWT]",
    },
    {
        "name": "private_key_block",
        "regex": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
        "replacement": "[REDACTED:PRIVATE_KEY]",
    },
    {
        "name": "url_password",
        "regex": r"://[^\s:@/]+:([^@\s/]+)@",
        "replacement": "://user:[REDACTED:URL_PASSWORD]@",
    },
]

CATALOG_VERSION = "1"


def load_catalog(path: str | None = None) -> dict:
    """Load patterns from a JSON file, or return defaults."""
    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "patterns" in data:
            return data
    return {"version": CATALOG_VERSION, "patterns": DEFAULT_PATTERNS}


def compile_patterns(catalog: dict) -> list[tuple[str, "re.Pattern", str]]:
    out = []
    for p in catalog.get("patterns", []):
        try:
            out.append((p["name"], re.compile(p["regex"]), p["replacement"]))
        except (re.error, KeyError):
            pass
    return out
