"""Thin Mode router over precomputed Intelligence Core snapshots."""

from __future__ import annotations

from ..models import Mode
from .analyst import build_analyst_report
from .compare import build_compare_report
from .contracts import ModeRequest, ModeResponse, utc_now
from .core import IntelligenceCoreSnapshot, evidence_references
from .creator import build_creator_brief
from .player import build_player_report


def _brief_reason(reason: str | None, limit: int = 240) -> str:
    if not reason:
        return ""
    compact = " ".join(reason.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _validate_contexts(
    request: ModeRequest,
    contexts: list[IntelligenceCoreSnapshot],
) -> None:
    if len(contexts) != len(request.games):
        raise ValueError("Mode request game count does not match supplied Intelligence Core snapshots")
    available = {context.game.game_id for context in contexts}
    for reference in request.games:
        if reference.startswith("game_") and reference not in available:
            raise ValueError(f"no Intelligence Core snapshot supplied for {reference}")


def route_mode(
    request: ModeRequest,
    contexts: list[IntelligenceCoreSnapshot],
) -> ModeResponse:
    """Render a Mode without invoking resolver, retrieval, relevance, or annotation."""

    _validate_contexts(request, contexts)
    if request.mode == Mode.PLAYER:
        report = build_player_report(contexts[0], request.preferences)
        payload = report.to_dict()
    elif request.mode == Mode.CREATOR:
        payload = build_creator_brief(contexts[0]).to_dict()
    elif request.mode == Mode.ANALYST:
        payload = build_analyst_report(contexts[0]).to_dict()
    elif request.mode == Mode.COMPARE:
        payload = build_compare_report(contexts, request.preferences).to_dict()
    else:
        raise NotImplementedError(
            f"{request.mode.value} Mode is not enabled yet; complete its ordered Issue first"
        )
    evidence_ids = {
        evidence_id
        for value in _walk(payload)
        if isinstance(value, dict)
        for evidence_id in value.get("evidence_ids", [])
    }
    limitations = [
        "Public community evidence is self-selected and not population-representative.",
        "Missing evidence is reported as insufficient, never converted into a neutral fit.",
    ]
    for context in contexts:
        for source in context.insight_bundle.coverage.sources:
            if source.status in {"partial", "unavailable", "failed", "disabled"}:
                limitations.append(
                    f"{context.game.canonical_title}: {source.source} is {source.status}"
                    + (f" ({_brief_reason(source.reason)})" if source.reason else "")
                )
    return ModeResponse(
        request_id=request.request_id,
        mode=request.mode,
        game_ids=[context.game.game_id for context in contexts],
        payload=payload,
        source_coverage={
            context.game.game_id: context.insight_bundle.coverage for context in contexts
        },
        limitations=list(dict.fromkeys(limitations)),
        evidence_references=evidence_references(contexts, evidence_ids),
        generated_at=utc_now(),
    )


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
