"""CORE v2.0 Agent Router — determines target agent for inbound messages.

Routing priority (v2.0.4):
  1. Rule-based: metadata conditions (workflow_pointer, context_id, metadata_tags)
     — checked BEFORE explicit agentId, since agentId may target wrong peer
  2. Rule-based: text content (pattern, tags)
  3. Explicit agentId in metadata — only when no rule matched
  4. Default agent
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
    # v2.0.4: metadata-based matching
    match_context_id: str | None = None
    match_has_workflow_pointer: bool = False
    match_tags_in_metadata: list[str] = field(default_factory=list)
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
            match_conf = r.get("match", {})
            target = r.get("target", {})
            parsed.append(RoutingRule(
                name=r.get("name", ""),
                pattern=match_conf.get("pattern"),
                tags=match_conf.get("tags", []),
                skills=match_conf.get("skills", []),
                # v2.0.4: metadata-based routing
                match_context_id=match_conf.get("context_id"),
                match_has_workflow_pointer=bool(match_conf.get("has_workflow_pointer")),
                match_tags_in_metadata=match_conf.get("metadata_tags", []),
                target_peer=target.get("peer", self.default_peer),
                target_agent_id=target.get("agent_id", self.default_agent_id),
                priority=r.get("priority", 0),
            ))
        parsed.sort(key=lambda r: -r.priority)
        self._rules = parsed
        log.info("loaded %d routing rules", len(parsed))

    def route(self, text: str = "", metadata: dict | None = None) -> RoutingResult:
        """Determine target agent for a message.

        Routing priority (v2.0.4):
          1. Rule-based: metadata conditions — checked BEFORE explicit agentId
          2. Rule-based: text content (pattern, tags)
          3. Explicit agentId in metadata — only when no rule matched
          4. Default agent

        Args:
            text: Message text content for rule matching.
            metadata: Message metadata dict.

        Returns:
            RoutingResult with peer and agent_id.
        """
        sorted_rules = sorted(self._rules, key=lambda r: -r.priority)
        text_lower = text.lower() if text else ""

        # Priority 1: metadata conditions in routing rules (v2.0.4)
        for rule in sorted_rules:
            if self._rule_matches_metadata(rule, metadata):
                log.info("routing via rule '%s' (metadata match)", rule.name)
                return RoutingResult(
                    peer=rule.target_peer,
                    agent_id=rule.target_agent_id,
                    rule_name=rule.name,
                )

        # Priority 2: text content matching (pattern, tags)
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

        # Priority 3: explicit agentId in metadata (only when no rule matched)
        if metadata:
            agent_id = (
                metadata.get("agentId")
                or metadata.get("agent_id")
                or (metadata.get("workflow_pointer") or {}).get("next_agent")
            )
            if agent_id:
                log.info("routing via explicit agentId: %s", agent_id)
                return RoutingResult(
                    peer=metadata.get("peer", self.default_peer),
                    agent_id=str(agent_id),
                    rule_name="explicit_agent_id",
                )

        # Priority 4: default agent
        log.info("routing via default agent: %s@%s", self.default_agent_id, self.default_peer)
        return RoutingResult(
            peer=self.default_peer,
            agent_id=self.default_agent_id,
            rule_name="default",
        )

    def _rule_matches_metadata(self, rule: RoutingRule, metadata: dict | None) -> bool:
        """v2.0.4: Check if a routing rule's metadata conditions match."""
        if not isinstance(metadata, dict):
            return False
        # context_id exact match
        if rule.match_context_id:
            ctx = str(metadata.get("context_id") or metadata.get("contextId") or "")
            if ctx != rule.match_context_id:
                return False
        # has_workflow_pointer
        if rule.match_has_workflow_pointer:
            if not metadata.get("workflow_pointer"):
                return False
        # metadata_tags: tag values checked against metadata dict values (string only)
        if rule.match_tags_in_metadata:
            meta_vals = [str(v).lower() for v in metadata.values() if isinstance(v, str)]
            if not any(tag.lower() in val for tag in rule.match_tags_in_metadata for val in meta_vals):
                return False
        return True
