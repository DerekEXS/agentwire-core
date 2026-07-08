"""CORE v2.0 Agent Card — A2A protocol discovery endpoint."""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
)


def build_agent_card(
    name: str = "AgentWire Gateway",
    version: str = "2.0.2",
    listen_host: str = "127.0.0.1",
    listen_port: int = 18800,
) -> AgentCard:
    """Build the standard A2A Agent Card for the gateway.

    Skills are declared statically; registered peer agents augment
    capabilities at runtime via the extended agent card endpoint.
    """
    base_url = f"http://{listen_host}:{listen_port}"

    return AgentCard(
        name=name,
        description=(
            "AgentWire Gateway v2.0 — A2A v1.0 compliant message router. "
            "Receives A2A messages, routes to registered agents via "
            "rule-based or explicit agentId dispatch, manages Task lifecycle."
        ),
        version=version,
        supported_interfaces=[
            AgentInterface(
                url=f"{base_url}/a2a/jsonrpc",
                protocol_binding="jsonrpc",
                protocol_version="1.0",
            ),
        ],
        provider=AgentProvider(
            url="https://github.com/DerekEXS/agentwire-core",
            organization="AgentWire",
        ),
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            extended_agent_card=False,
        ),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id="message_routing",
                name="Message Routing",
                description="Route A2A messages to registered agents based on explicit agentId or content-based rules",
                tags=["routing", "dispatch", "a2a"],
                input_modes=["text"],
                output_modes=["text"],
            ),
            AgentSkill(
                id="task_management",
                name="Task Management",
                description="Standard A2A Task lifecycle: submitted → working → completed/failed/cancelled",
                tags=["task", "lifecycle", "state-machine"],
                input_modes=["text"],
                output_modes=["text"],
            ),
            AgentSkill(
                id="peer_registry",
                name="Peer Registry",
                description="Maintain registry of connected A2A peers with their agent cards and capabilities",
                tags=["peer", "discovery", "registry"],
                input_modes=["text"],
                output_modes=["text"],
            ),
        ],
    )
