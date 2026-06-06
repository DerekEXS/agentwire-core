"""History persistence: per-peer JSONL files + index.

One JSONL file per peer, named by UUID (sha256 prefix of context_id).
Index at index.json maintains peer metadata (display name, last_round,
total_rounds, first_round, last_ts, file path).

Rounds are auto-incremented on every outbound message; inbound messages
attach to the most recent round started by the same peer. Orphan
inbound (no matching outbound) gets a synthetic outbound placeholder.

FIFO: when max_rounds_per_peer > 0 and total_rounds exceeds it, drop
the oldest 2-line pair and bump first_round. Round numbers never
recycle.
"""
import hashlib
import json
import re
import time
from pathlib import Path
from threading import RLock


def _peer_uuid_from_context(context_id: str | None, fallback: str) -> str:
    """Derive a stable peer UUID. Uses context_id if present, else hash
    of the fallback (e.g. message id). 16 hex chars.
    """
    src = (context_id or fallback or "default").encode("utf-8")
    return hashlib.sha256(src).hexdigest()[:16]


class HistoryManager:
    def __init__(self, storage_dir: str, max_rounds_per_peer: int = 0):
        self.dir = Path(storage_dir).expanduser()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_rounds = max_rounds_per_peer  # 0 = unlimited
        self.index_path = self.dir / "index.json"
        self.lock = RLock()
        self._patterns: list[tuple[str, "re.Pattern", str]] = []
        self._index: dict = self._load_index()

    def _load_index(self) -> dict:
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"peers": {}}
        return {"peers": {}}

    def _save_index(self) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._index, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.index_path)

    def _peer_file(self, peer_uuid: str) -> Path:
        return self.dir / f"peer_{peer_uuid}.jsonl"

    def _redact(self, text: str) -> str:
        for _name, pattern, repl in self._patterns:
            text = pattern.sub(repl, text)
        return text

    def _redact_parts(self, parts: list[dict]) -> list[dict]:
        if not self._patterns:
            return parts
        out = []
        for p in parts:
            if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str):
                redacted = dict(p)
                redacted["text"] = self._redact(p["text"])
                out.append(redacted)
            else:
                out.append(p)
        return out

    def set_patterns(self, patterns: list[dict]) -> None:
        """Hot-swap redaction patterns (e.g. after fetching /redact/patterns)."""
        with self.lock:
            self._patterns = []
            for p in patterns:
                try:
                    self._patterns.append((p["name"], re.compile(p["regex"]), p["replacement"]))
                except (re.error, KeyError) as e:
                    # Skip malformed pattern, keep going
                    pass

    def get_or_create_peer(self, peer_uuid: str, peer_name: str | None = None) -> dict:
        with self.lock:
            peer = self._index["peers"].get(peer_uuid)
            if peer is None:
                peer = {
                    "uuid": peer_uuid,
                    "name": peer_name or peer_uuid[:8],
                    "last_round": 0,
                    "first_round": 0,
                    "total_rounds": 0,
                    "last_ts": None,
                    "file": f"peer_{peer_uuid}.jsonl",
                }
                self._index["peers"][peer_uuid] = peer
            elif peer_name and peer_name != peer["name"]:
                # Update display name on every contact (covers name changes)
                peer["name"] = peer_name
            return peer

    def _append_line(self, peer_uuid: str, line: dict) -> None:
        path = self._peer_file(peer_uuid)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def _read_all_lines(self, peer_uuid: str) -> list[dict]:
        path = self._peer_file(peer_uuid)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _enforce_cap(self, peer: dict) -> None:
        if self.max_rounds <= 0:
            return
        if peer["total_rounds"] <= self.max_rounds:
            return
        path = self._peer_file(peer["uuid"])
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").splitlines(keepends=False)
        # Each round is 2 lines. Drop oldest (total_rounds - max_rounds) rounds.
        drop = peer["total_rounds"] - self.max_rounds
        keep_from = drop * 2
        new_lines = lines[keep_from:]
        # Atomic rewrite
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
        tmp.replace(path)
        peer["first_round"] += drop

    def record_outbound(
        self,
        context_id: str | None,
        msg_id: str,
        parts: list[dict],
    ) -> tuple[str, int]:
        """Record an outbound message; returns (peer_uuid, round)."""
        peer_uuid = _peer_uuid_from_context(context_id, msg_id)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.lock:
            peer = self.get_or_create_peer(peer_uuid)
            # New round for new outbound
            round_n = peer["last_round"] + 1
            peer["last_round"] = round_n
            peer["total_rounds"] += 1
            peer["last_ts"] = ts
            line = {
                "round": round_n,
                "ts": ts,
                "role": "outbound",
                "msg_id": msg_id,
                "context_id": context_id,
                "peer_uuid": peer_uuid,
                "peer_name": peer["name"],
                "parts": self._redact_parts(parts),
            }
            self._append_line(peer_uuid, line)
            self._enforce_cap(peer)
            self._save_index()
            return peer_uuid, round_n

    def record_inbound(
        self,
        peer_uuid: str,
        msg_id: str,
        parts: list[dict],
    ) -> int:
        """Record an inbound message; attaches to the current (or last) round."""
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.lock:
            peer = self.get_or_create_peer(peer_uuid)
            round_n = peer["last_round"]  # Attach to current round
            line = {
                "round": round_n,
                "ts": ts,
                "role": "inbound",
                "msg_id": msg_id,
                "context_id": None,
                "peer_uuid": peer_uuid,
                "peer_name": peer["name"],
                "parts": self._redact_parts(parts),
            }
            self._append_line(peer_uuid, line)
            self._save_index()
            return round_n

    def list_messages(
        self,
        peer_uuid: str | None = None,
        since_round: int = 0,
        limit: int = 5,
    ) -> dict:
        with self.lock:
            if peer_uuid is None:
                # Aggregate over all peers
                out = {"peers": []}
                for uuid_, p in self._index["peers"].items():
                    msgs = self._read_all_lines(uuid_)
                    # Last `limit` rounds
                    cutoff = max(p["last_round"] - limit + 1, p["first_round"])
                    msgs = [m for m in msgs if m["round"] >= cutoff and m["round"] >= since_round]
                    out["peers"].append({
                        "peer_uuid": uuid_,
                        "peer_name": p["name"],
                        "first_round": p["first_round"],
                        "last_round": p["last_round"],
                        "total_rounds": p["total_rounds"],
                        "messages": msgs,
                    })
                return out
            peer = self._index["peers"].get(peer_uuid)
            if not peer:
                return {
                    "peer_uuid": peer_uuid,
                    "peer_name": None,
                    "first_round": 0,
                    "last_round": 0,
                    "total_rounds": 0,
                    "messages": [],
                }
            msgs = self._read_all_lines(peer_uuid)
            cutoff = max(peer["last_round"] - limit + 1, peer["first_round"], since_round)
            msgs = [m for m in msgs if m["round"] >= cutoff]
            return {
                "peer_uuid": peer_uuid,
                "peer_name": peer["name"],
                "first_round": peer["first_round"],
                "last_round": peer["last_round"],
                "total_rounds": peer["total_rounds"],
                "messages": msgs,
            }

    def get_round(self, peer_uuid: str, round_n: int) -> list[dict]:
        with self.lock:
            msgs = self._read_all_lines(peer_uuid)
            return [m for m in msgs if m["round"] == round_n]

    def list_peers(self) -> list[dict]:
        with self.lock:
            return [
                {
                    "uuid": p["uuid"],
                    "name": p["name"],
                    "last_round": p["last_round"],
                    "total_rounds": p["total_rounds"],
                    "last_ts": p["last_ts"],
                }
                for p in self._index["peers"].values()
            ]

    def get_context_for_peer(self, peer_uuid: str, n_rounds: int) -> list[dict]:
        """Return the last N rounds of messages for a peer (used for
        context-injection in outbound messages). Returns [] if n_rounds
        is 0 or peer unknown.
        """
        if n_rounds <= 0:
            return []
        with self.lock:
            peer = self._index["peers"].get(peer_uuid)
            if not peer:
                return []
            msgs = self._read_all_lines(peer_uuid)
            cutoff = max(peer["last_round"] - n_rounds + 1, peer["first_round"])
            return [m for m in msgs if m["round"] >= cutoff]

    def export(self, peer_uuid: str, fmt: str = "jsonl") -> str:
        with self.lock:
            msgs = self._read_all_lines(peer_uuid)
            if fmt == "jsonl":
                return "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs)
            if fmt == "markdown":
                peer = self._index["peers"].get(peer_uuid, {})
                lines = [f"# Conversation with {peer.get('name', peer_uuid)}", ""]
                current_round = None
                for m in msgs:
                    if m["round"] != current_round:
                        current_round = m["round"]
                        lines.append(f"\n## Round {m['round']} — {m['ts']}\n")
                    role = m["role"].capitalize()
                    text = " ".join(p.get("text", "") for p in m.get("parts", []) if p.get("type") == "text")
                    lines.append(f"- **{role}**: {text}\n")
                return "\n".join(lines)
            raise ValueError(f"unknown format: {fmt}")
