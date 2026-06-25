import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Awaitable, Callable, Optional

from core.observability import build_query_rewriting_debug, elapsed_ms
from prompts.query_rewrite_prompt import build_query_rewrite_prompt
from services.llm_provider import LLMProvider
from services.providers.ollama_provider import OllamaProvider
from services.providers.llama_cpp_provider import LlamaCppProvider

FOLLOW_UP_PATTERN = re.compile(
    r"\b("
    r"it|its|this|that|these|those|they|them|their|there|"
    r"same|also|another|more|else|above|earlier|previous|"
    r"instead|otherwise|again|still|either|neither"
    r")\b",
    re.IGNORECASE,
)
FOLLOW_UP_PREFIX_PATTERN = re.compile(
    r"^(and|but|so|what about|how about|why about)\b",
    re.IGNORECASE,
)


@dataclass
class QueryRewriteOutcome:
    enabled: bool
    used: bool
    original_question: str
    rewritten_query: str
    history_turns_used: int
    latency_ms: float

    def to_debug(self) -> dict[str, Any]:
        return build_query_rewriting_debug(
            enabled=self.enabled,
            used=self.used,
            original_question=self.original_question,
            rewritten_query=self.rewritten_query,
            history_turns_used=self.history_turns_used,
            latency_ms=self.latency_ms,
        )


def format_history_turns(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def count_history_turns(messages: list[dict[str, Any]]) -> int:
    turns = 0
    pending_user = False
    for message in messages:
        role = message.get("role")
        if role == "user":
            pending_user = True
        elif role == "assistant" and pending_user:
            turns += 1
            pending_user = False
    return turns


def trim_history_messages(
    messages: list[dict[str, Any]], max_turns: int
) -> list[dict[str, Any]]:
    if max_turns <= 0 or not messages:
        return []

    pairs: list[list[dict[str, Any]]] = []
    pending_user: dict[str, Any] | None = None

    for message in messages:
        role = message.get("role")
        if role == "user":
            pending_user = message
        elif role == "assistant" and pending_user is not None:
            pairs.append([pending_user, message])
            pending_user = None

    selected_pairs = pairs[-max_turns:]
    return [message for pair in selected_pairs for message in pair]


def is_context_dependent(question: str) -> bool:
    normalized = question.strip()
    if not normalized:
        return False

    if FOLLOW_UP_PREFIX_PATTERN.search(normalized):
        return True

    return bool(FOLLOW_UP_PATTERN.search(normalized))


def normalize_rewritten_query(text: str) -> str:
    cleaned = text.strip().strip("\"'`")
    if not cleaned:
        return ""
    first_line = cleaned.splitlines()[0].strip()
    return first_line.rstrip(".")


class QueryRewriter:
    def __init__(
        self,
        *,
        enabled: bool,
        history_turns: int,
        llm_provider: Optional[LLMProvider] = None,
        rewrite_model: Optional[str] = None,
        rewrite_model_resolver: Optional[Callable[[], str]] = None,
        generate_fn: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> None:
        self.enabled = enabled
        self.history_turns = history_turns
        self._llm_provider = llm_provider
        self._rewrite_model = rewrite_model
        self._rewrite_model_resolver = rewrite_model_resolver
        self._generate_fn = generate_fn

    def _resolve_rewrite_model(self) -> Optional[str]:
        if self._rewrite_model_resolver is not None:
            return self._rewrite_model_resolver()
        return self._rewrite_model

    async def rewrite(
        self, question: str, history: list[dict[str, Any]]
    ) -> QueryRewriteOutcome:
        original = question.strip()
        disabled = QueryRewriteOutcome(
            enabled=False,
            used=False,
            original_question=original,
            rewritten_query=original,
            history_turns_used=0,
            latency_ms=0.0,
        )

        if not self.enabled:
            return disabled

        trimmed = trim_history_messages(history, self.history_turns)
        if not trimmed:
            return QueryRewriteOutcome(
                enabled=True,
                used=False,
                original_question=original,
                rewritten_query=original,
                history_turns_used=0,
                latency_ms=0.0,
            )

        if not is_context_dependent(original):
            return QueryRewriteOutcome(
                enabled=True,
                used=False,
                original_question=original,
                rewritten_query=original,
                history_turns_used=count_history_turns(trimmed),
                latency_ms=0.0,
            )

        started = perf_counter()
        history_text = format_history_turns(trimmed)
        prompt = build_query_rewrite_prompt(original, history_text)
        rewritten = normalize_rewritten_query(await self._generate(prompt))
        latency_ms = elapsed_ms(started, perf_counter())

        if not rewritten:
            rewritten = original

        used = rewritten.casefold() != original.casefold()
        return QueryRewriteOutcome(
            enabled=True,
            used=used,
            original_question=original,
            rewritten_query=rewritten,
            history_turns_used=count_history_turns(trimmed),
            latency_ms=latency_ms,
        )

    async def _generate(self, prompt: str) -> str:
        if self._generate_fn is not None:
            return await self._generate_fn(prompt)

        if self._llm_provider is None:
            raise RuntimeError("Query rewriting requires an LLM provider or test generate_fn.")

        rewrite_model = self._resolve_rewrite_model()
        if rewrite_model and rewrite_model != self._llm_provider.model:
            if isinstance(self._llm_provider, (OllamaProvider, LlamaCppProvider)):
                rewrite_provider = self._llm_provider.with_model(rewrite_model)
                return await rewrite_provider.generate(prompt)
            raise RuntimeError(
                "Dedicated rewrite model requires a local provider with model override support."
            )

        return await self._llm_provider.generate(prompt)
