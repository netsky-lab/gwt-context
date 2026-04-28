"""Infrastructure adapters for external broadcast-bus subscribers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from gwt_context.application.broadcast_bus import (
    BroadcastContext,
    BroadcastProposal,
    ExternalReasoningSubscriber,
)


class ChatCompletionClient(Protocol):
    """Small boundary for OpenAI-compatible chat completion transports."""

    def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Return assistant text for a chat-completion request."""
        ...


@dataclass(frozen=True)
class OpenAICompatibleSubscriberConfig:
    """Configuration for an OpenAI-compatible subscriber transport."""

    api_base: str
    model: str
    api_key: str = "not-needed"
    timeout_seconds: float = 10.0


class OpenAICompatibleChatClient:
    """Minimal stdlib OpenAI-compatible chat client.

    The application layer never sees this class. It belongs at the infrastructure
    edge and returns raw assistant text to the JSON proposal adapter.
    """

    def __init__(self, config: OpenAICompatibleSubscriberConfig) -> None:
        self._config = config

    def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Call `/chat/completions` and return the first assistant message."""
        endpoint = self._chat_endpoint()
        payload = json.dumps(
            {
                "model": self._config.model,
                "messages": list(messages),
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - user-configured benchmark endpoint.
                request,
                timeout=self._config.timeout_seconds,
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"external subscriber request failed: {exc}") from exc
        return _assistant_text(data)

    def _chat_endpoint(self) -> str:
        base = self._config.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"


class JsonProposalAdapter:
    """Convert external JSON responses into broadcast proposals."""

    def __init__(self, client: ChatCompletionClient) -> None:
        self._client = client

    def __call__(self, context: BroadcastContext) -> Sequence[BroadcastProposal]:
        """Ask the external processor for proposal JSON and parse safe proposals."""
        response_text = self._client.complete(_proposal_messages(context))
        payload = _load_json_object(response_text)
        raw_proposals = payload.get("proposals", [])
        if not isinstance(raw_proposals, list):
            return ()
        proposals = [_parse_proposal(item) for item in raw_proposals]
        return tuple(proposal for proposal in proposals if proposal is not None)


def build_openai_compatible_subscriber(
    name: str,
    config: OpenAICompatibleSubscriberConfig,
    *,
    min_priority: float = 0.5,
) -> ExternalReasoningSubscriber:
    """Build a port-safe external subscriber from OpenAI-compatible config."""
    return ExternalReasoningSubscriber(
        name,
        JsonProposalAdapter(OpenAICompatibleChatClient(config)),
        min_priority=min_priority,
    )


def _proposal_messages(context: BroadcastContext) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an independent post-broadcast processor. Return JSON only "
                "with a top-level proposals array. Each proposal must include kind, "
                "priority, rationale, and payload. Allowed kinds: query_memory, "
                "resolve_answer, flag_contradiction, ask_followup."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {context.question}\n"
                f"Pass: {context.pass_number}\n"
                f"Broadcast:\n{context.broadcast_text}\n\n"
                f"Context chunks:\n{json.dumps(list(context.context_chunks), ensure_ascii=True)}"
            ),
        },
    ]


def _parse_proposal(value: object) -> BroadcastProposal | None:
    if not isinstance(value, Mapping):
        return None
    kind = str(value.get("kind", "")).strip()
    rationale = str(value.get("rationale", "")).strip()
    if not kind or not rationale:
        return None
    try:
        priority = float(value.get("priority", 0.0))
    except (TypeError, ValueError):
        return None
    raw_payload = value.get("payload", {})
    payload: Mapping[str, Any] = raw_payload if isinstance(raw_payload, Mapping) else {}
    return BroadcastProposal(
        subscriber="external",
        kind=kind,
        priority=max(0.0, min(1.0, priority)),
        rationale=rationale,
        payload=payload,
    )


def _load_json_object(text: str) -> dict[str, Any]:
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise RuntimeError("external subscriber response must be a JSON object")
    return loaded


def _assistant_text(data: Any) -> str:
    if not isinstance(data, Mapping):
        raise RuntimeError("chat completion response must be a JSON object")
    choices = data.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("chat completion response did not include choices")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise RuntimeError("chat completion choice must be an object")
    message = first.get("message", {})
    if not isinstance(message, Mapping):
        raise RuntimeError("chat completion message must be an object")
    content = message.get("content", "")
    if not isinstance(content, str) or not content:
        raise RuntimeError("chat completion message content was empty")
    return content
