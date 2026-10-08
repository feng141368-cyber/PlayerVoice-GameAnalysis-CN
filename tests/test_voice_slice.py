from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gamepulse.collectors.base import (
    ADAPTER_CONTRACT_VERSION,
    AuthModel,
    BaseSourceAdapter,
    PaginationModel,
    QueryStyle,
    RetrievalContext,
    SourceCapabilities,
    SourcePage,
    SourceStatus,
    make_provenance,
    stable_evidence_id,
)
from gamepulse.foundation import FoundationResult
from gamepulse.models import EvidenceItem, GameEntity, QueryPlan
from gamepulse.voice_slice import run_voice_slice


ROOT = Path(__file__).resolve().parents[1]


class FixtureCommunityAdapter(BaseSourceAdapter):
    def __init__(self, source: str, game: GameEntity, plan: QueryPlan):
        self.name = source
        self.game = game
        self.plan = plan

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source=self.name,
            evidence_kinds=["review" if self.name == "steam" else "comment"],
            auth_model=AuthModel.NONE,
            pagination=PaginationModel.NONE,
            supported_query_styles=[QueryStyle.ENTITY_ID if self.name == "steam" else QueryStyle.TEXT_SEARCH],
            languages=[self.plan.language],
            supported_intents=[self.plan.intent.value],
            rate_limit={},
            live_retrieval=False,
            availability_notes="Deterministic CI fixture adapter",
        )

    def search(self, plan: QueryPlan, cursor: str | None = None) -> SourcePage:
        return SourcePage(
            source=self.name,
            status=SourceStatus.COLLECTED,
            cursor=cursor,
            native_items=[{"source_content_id": hashlib.sha256(plan.query_id.encode()).hexdigest()[:12]}],
            requests_made=1,
        )

    def normalize(self, native_item: dict, context: RetrievalContext) -> EvidenceItem:
        source_id = native_item["source_content_id"]
        positive = self.plan.intent.value == "general"
        if self.plan.language.casefold().startswith("zh"):
            text = "核心玩法很好玩。" if positive else "新版本更新后掉帧卡顿，表现很糟糕。"
        else:
            text = "The gameplay is great and fun." if positive else "The update caused terrible FPS stutter."
        metadata = {"query_provenance": context.query_provenance}
        if self.name == "steam":
            metadata["app_id"] = self.game.external_ids.get("steam_app_id")
        return EvidenceItem(
            evidence_id=stable_evidence_id(self.name, source_id),
            game_id=self.game.game_id,
            evidence_kind="review" if self.name == "steam" else "comment",
            access_scope="public",
            dataset_id=None,
            source=self.name,
            source_content_id=source_id,
            source_url=f"https://example.test/{self.name}/{source_id}",
            source_reference=None,
            title=self.game.canonical_title,
            original_text=text,
            normalized_text=None,
            language=self.plan.language,
            published_at=context.retrieved_at,
            retrieved_at=context.retrieved_at,
            run_id=context.run_id,
            query_id=self.plan.query_id,
            matched_alias_ids=list(self.plan.alias_ids),
            retrieval_method="public_endpoint",
            relevance_label="pending",
            relevance_score=None,
            relevance_reasons=["fixture retrieval"],
            relevance_method_version=None,
            recommended=positive if self.name == "steam" else None,
            platform=self.name,
            source_metadata=metadata,
            provenance=make_provenance(
                source_class="platform_store" if self.name == "steam" else "public_community",
                collector_version=ADAPTER_CONTRACT_VERSION,
                text=text,
                raw_snapshot_reference=None,
                terms_or_permission_reference="CI fixture",
            ),
        )


def foundation(filename: str) -> FoundationResult:
    payload = json.loads((ROOT / "examples/foundation" / filename).read_text(encoding="utf-8"))
    return FoundationResult.model_validate(payload)


class VoiceSliceTests(unittest.TestCase):
    def test_three_fixture_games_complete_issue_1_to_10_slice(self):
        cases = [
            ("无限暖暖", "infinity-nikki.json"),
            ("PUBG: BATTLEGROUNDS", "pubg-battlegrounds.json"),
            ("Counter-Strike 2", "counter-strike-2.json"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (name, filename) in enumerate(cases):
                with self.subTest(game=name):
                    result = run_voice_slice(
                        name,
                        root / str(index),
                        foundation=foundation(filename),
                        sources=["steam", "bilibili"],
                        intents=["general", "performance"],
                        max_plans_per_source=2,
                        adapter_factory=lambda source, entity, plan, config: FixtureCommunityAdapter(
                            source, entity, plan
                        ),
                        run_id=f"run_fixture_{index}",
                    )
                    self.assertEqual(result.foundation.resolution.status.value, "resolved")
                    self.assertTrue(result.foundation.aliases.aliases)
                    self.assertTrue(result.query_plans)
                    self.assertGreater(result.raw_community_items, 0)
                    self.assertGreater(result.relevance_counts.get("relevant", 0), 0)
                    self.assertGreater(result.corpus.relevant_items, 0)
                    self.assertEqual(result.annotation_count, result.insights.coverage.relevant_corpus_size)
                    self.assertIsNotNone(result.annotations_path)
                    annotation_lines = Path(result.annotations_path).read_text(encoding="utf-8").splitlines()
                    self.assertEqual(len(annotation_lines), result.annotation_count)
                    coverage = {value.source: value for value in result.insights.coverage.sources}
                    for source, execution in result.source_execution.items():
                        self.assertEqual(coverage[source].items_retrieved, execution.raw_items)
                    self.assertEqual(coverage["official"].items_retrieved, 1)
                    self.assertTrue(result.insights.player_insights)
                    self.assertTrue(Path(result.report_path).exists())
                    self.assertTrue(all(insight.supporting_evidence_ids for insight in result.insights.player_insights))

    def test_cs2_scoped_alias_is_not_used_as_standalone_query(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_voice_slice(
                "Counter-Strike 2",
                Path(directory),
                foundation=foundation("counter-strike-2.json"),
                sources=["bilibili"],
                intents=["performance"],
                max_plans_per_source=4,
                adapter_factory=lambda source, entity, plan, config: FixtureCommunityAdapter(source, entity, plan),
                run_id="run_fixture_cs2",
            )
        cs2_plans = [plan for plan in result.query_plans if "CS2" in plan.query_text]
        self.assertTrue(cs2_plans)
        self.assertTrue(all("Counter-Strike 2" in plan.query_text for plan in cs2_plans))


if __name__ == "__main__":
    unittest.main()
