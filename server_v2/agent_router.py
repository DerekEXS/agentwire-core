"""CORE v2.0 Agent Router — determines target agent for inbound messages.

Routing priority:
  1. Explicit agentId in message metadata
  2. Rule-based: keyword/skill pattern matching (YAML config)
  3. Default agent (configurable fallback)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

log = logging.getLogger("agentwire.router")


@dataclass
class RoutingRule:
    name: str
    pattern: str | None = None
    tags: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    target_peer: str = ""
    target_agent_id: str = ""
    priority: int = 0


@dataclass
class RoutingResult:
    peer: str
    agent_id: str
    rule_name: str = ""


class AgentRouter:
    """Resolve which agent should handle an inbound message."""

    def __init__(
        self,
        config_path: str | None = None,
        default_agent_id: str = "main",
        default_peer: str = "openclaw",
    ):
        self.default_agent_id = default_agent_id
        self.default_peer = default_peer
        self._rules: list[RoutingRule] = []
        if config_path:
            self.load_rules(config_path)

    def load_rules(self, config_path: str) -> None:
        """Load routing rules from YAML config file."""
        path = Path(config_path)
        if not path.exists():
            log.info("no routing config at %s, using default agent", config_path)
            return
        try:
            with open(path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            log.error("failed to load routing config: %s", e)
            return

        raw_rules = cfg.get("routing_rules", []) or []
        parsed = []
        for r in raw_rules:
            match = r.get("match", {})
            target = r.get("target", {})
            parsed.append(RoutingRule(
                name=r.get("name", ""),
                pattern=match.get("pattern"),
                tags=match.get("tags", []),
                skills=match.get("skills", []),
                target_peer=target.get("peer", self.default_peer),
                target_agent_id=target.get("agent_id", self.default_agent_id),
                priority=r.get("priority", 0),
            ))
        parsed.sort(key=lambda r: -r.priority)
        self._rules = parsed
        log.info("loaded %d routing rules", len(parsed))

    def route(self, text: str = "", metadata: dict | None = None) -> RoutingResult:
        """Determine target agent for a message.

        Args:
            text: Message text content for rule matching.
            metadata: Message metadata dict (may contain explicit agentId).

        Returns:
            RoutingResult with peer and agent_id.
        """
        # Priority 1: explicit agentId in metadata
        if metadata:
            agent_id = (
                metadata.get("agentId")
                or metadata.get("agent_id")
                or metadata.get("workflow_pointer", {}).get("next_agent")
            )
            if agent_id:
                log.info("routing via explicit agentId: %s", agent_id)
                return RoutingResult(
                    peer=metadata.get("peer", self.default_peer),
                    agent_id=str(agent_id),
                    rule_name="explicit_agent_id",
                )

        # Priority 2: rule-based matching (sorted by descending priority)
        if text and self._rules:
            text_lower = text.lower()
            sorted_rules = sorted(self._rules, key=lambda r: -r.priority)
            for rule in sorted_rules:
                if rule.pattern:
                    try:
                        if re.search(rule.pattern, text, re.IGNORECASE):
                            log.info("routing via rule '%s' (pattern match)", rule.name)
                            return RoutingResult(
                                peer=rule.target_peer,
                                agent_id=rule.target_agent_id,
                                rule_name=rule.name,
                            )
                    except re.error:
                        log.warning("invalid regex in rule '%s': %s", rule.name, rule.pattern)
                if rule.tags:
                    if any(tag.lower() in text_lower for tag in rule.tags):
                        log.info("routing via rule '%s' (tag match: %s)", rule.name, rule.tags)
                        return RoutingResult(
                            peer=rule.target_peer,
                            agent_id=rule.target_agent_id,
                            rule_name=rule.name,
                        )

        # Priority 3: default agent
        log.info("routing via default agent: %s@%s", self.default_agent_id, self.default_peer)
        return RoutingResult(
            peer=self.default_peer,
            agent_id=self.default_agent_id,
            rule_name="default",
        )
