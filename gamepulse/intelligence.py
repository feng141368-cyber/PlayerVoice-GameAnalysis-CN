"""Transparent multi-label UGC annotation over the versioned taxonomy."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import Field, model_validator

from .models import AnalysisAnnotation, ContractModel, EvidenceItem, GameEntity, SentimentLabel


DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "config/taxonomy.yaml"
ANNOTATOR_VERSION = "transparent-rules-v1.1.1"


class TaxonomyTopic(ContractModel):
    id: str = Field(min_length=1)
    label_en: str = Field(min_length=1)
    label_zh: str = Field(min_length=1)
    definition: str | None = None
    parent: str | None = None
    extension: str | None = None


class TaxonomyDefinition(ContractModel):
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    core_topics: list[TaxonomyTopic]
    extension_topics: dict[str, list[TaxonomyTopic]]
    extension_triggers: dict[str, list[str]]
    behaviour_signal_ids: list[str]
    unknown_topic: str
    config_hash: str

    @model_validator(mode="after")
    def validate_topic_graph(self) -> "TaxonomyDefinition":
        all_topics = [*self.core_topics, *(topic for values in self.extension_topics.values() for topic in values)]
        ids = [topic.id for topic in all_topics]
        duplicates = sorted({topic_id for topic_id in ids if ids.count(topic_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate taxonomy topic IDs: {', '.join(duplicates)}")
        core_ids = {topic.id for topic in self.core_topics}
        if self.unknown_topic not in core_ids:
            raise ValueError(f"unknown topic {self.unknown_topic!r} is not a core topic")
        for topic in all_topics:
            if topic.parent and topic.parent not in set(ids):
                raise ValueError(f"topic {topic.id!r} has missing parent {topic.parent!r}")
        if len(self.behaviour_signal_ids) != len(set(self.behaviour_signal_ids)):
            raise ValueError("duplicate behaviour signal IDs")
        return self

    def active_topic_ids(self, game: GameEntity) -> set[str]:
        tags = {_normalise_tag(value) for value in game.genres}
        active = {topic.id for topic in self.core_topics}
        for extension, triggers in self.extension_triggers.items():
            if tags.intersection({_normalise_tag(value) for value in triggers}):
                active.update(topic.id for topic in self.extension_topics[extension])
        return active


def load_taxonomy(path: Path = DEFAULT_TAXONOMY_PATH) -> TaxonomyDefinition:
    raw = path.read_bytes()
    payload = yaml.safe_load(raw)
    if not isinstance(payload, dict):
        raise ValueError("taxonomy must be a YAML mapping")
    core_payload = payload.get("core_topics")
    if not isinstance(core_payload, list) or not core_payload:
        raise ValueError("taxonomy must define core_topics")
    core_topics = [TaxonomyTopic.model_validate(value) for value in core_payload]
    extensions: dict[str, list[TaxonomyTopic]] = {}
    triggers: dict[str, list[str]] = {}
    for extension, value in (payload.get("genre_extensions") or {}).items():
        if not isinstance(value, dict) or not isinstance(value.get("topics"), list):
            raise ValueError(f"genre extension {extension!r} must define topics")
        triggers[extension] = [str(item) for item in value.get("applies_when") or []]
        extensions[extension] = [
            TaxonomyTopic.model_validate({**topic, "extension": extension})
            for topic in value["topics"]
        ]
    behaviour = payload.get("behaviour_signals") or []
    behaviour_ids = [str(value["id"]) for value in behaviour]
    unknown_topic = str((payload.get("classification") or {}).get("unknown_topic") or "other_unclassified")
    return TaxonomyDefinition(
        version=str(payload.get("version") or ""),
        name=str(payload.get("name") or ""),
        core_topics=core_topics,
        extension_topics=extensions,
        extension_triggers=triggers,
        behaviour_signal_ids=behaviour_ids,
        unknown_topic=unknown_topic,
        config_hash=hashlib.sha256(raw).hexdigest()[:16],
    )


TOPIC_RULES: dict[str, list[str]] = {
    "gameplay": ["gameplay", "game loop", "mechanic", "玩法", "机制"],
    "combat": ["combat", "gunplay", "weapon", "recoil", "aiming", "boss fight", "damage", "战斗", "武器", "后坐力", "瞄准", "伤害", "闪避"],
    "exploration": ["exploration", "explore", "open world", "map discovery", "puzzle", "探索", "开放世界", "地图", "解谜"],
    "story": ["story", "plot", "narrative", "dialogue", "lore", "剧情", "主线", "叙事", "文案", "世界观"],
    "characters": ["character", "companion", "romance", "角色", "人物", "陪伴", "好感"],
    "progression": ["progression", "level up", "upgrade", "levelling", "养成", "升级", "突破", "进度"],
    "difficulty": ["difficulty", "too hard", "too easy", "difficulty spike", "skill gap", "难度", "太难", "太简单", "全是职业选手"],
    "grind": ["grind", "repetitive farm", "farming materials", "刷取", "重复刷", "肝", "材料"],
    "daily_commitment": ["daily chore", "daily quest", "every day", "weekly chore", "日常", "每天上线", "周常"],
    "endgame": ["endgame", "late game", "postgame", "终局", "后期内容", "长草"],
    "content_cadence": ["content drought", "update cadence", "new content", "内容更新", "更新节奏", "内容荒"],
    "monetisation": ["price", "expensive", "paywall", "battle pass", "subscription", "top up", "money grab", "价格", "氪金", "付费", "充值", "礼包", "月卡", "圈钱"],
    "gacha": ["gacha", "gachas", "pull", "pity", "banner", "抽卡", "抽不出来", "抽不到", "保底", "卡池", "出金"],
    "fomo": ["fomo", "limited time", "time limited", "限时", "错过", "限时活动"],
    "pvp": ["pvp", "ranked", "competitive", "player versus player", "竞技", "排位", "玩家对战"],
    "fair_play_integrity": ["cheater", "cheating", "anti-cheat", "anticheat", "bot lobby", "外挂", "作弊", "反作弊", "误封", "挂多", "人机太多"],
    "social": ["co-op", "coop", "guild", "friends", "chat", "multiplayer", "联机", "组队", "公会", "好友", "聊天"],
    "performance": ["performance", "frame rate", "frame drop", "stutter", "lag", "latency", "overheat", "loading", "optimisation", "optimization", "掉帧", "帧率", "卡顿", "延迟", "发热", "手机越来越烫", "越来越烫", "加载", "优化"],
    "graphics": ["graphics", "resolution", "texture", "ray tracing", "visual settings", "画质", "分辨率", "贴图", "光追"],
    "art_direction": ["art style", "art direction", "animation style", "美术", "画风", "动画风格"],
    "audio": ["audio", "sound", "音频", "声音"],
    "audio_music": ["music", "soundtrack", "score", "音乐", "配乐", "原声"],
    "audio_sound_design": ["sound effect", "mixing", "spatial audio", "音效", "混音", "空间音频"],
    "audio_voice_acting": ["voice acting", "voiceover", "dub", "配音", "声优"],
    "controls": ["controls", "controller", "keyboard", "mouse", "remap", "input lag", "操作", "手柄", "键鼠", "按键", "改键", "触控"],
    "ui_ux": ["ui", "interface", "menu", "inventory", "camera", "navigation", "界面", "菜单", "背包", "镜头", "导航"],
    "accessibility": ["accessibility", "colorblind", "subtitle size", "screen reader", "无障碍", "色盲", "字幕大小"],
    "bugs_stability": ["bug", "crash", "freeze", "freezes", "broken quest", "data loss", "闪退", "崩溃", "死机", "任务卡住", "数据丢失", "bug"],
    "compatibility": ["compatibility", "driver", "unsupported device", "operating system", "兼容", "驱动", "设备不支持"],
    "account_service": ["login", "account", "ban", "refund", "support ticket", "登录", "账号", "封号", "退款", "客服"],
    "onboarding": ["tutorial", "onboarding", "new player", "learning curve", "教程", "新手", "引导"],
    "return_experience": ["returning player", "catch up", "came back", "回流", "回坑", "追赶"],
    "patch_reaction": ["update", "patch", "hotfix", "new version", "更新", "补丁", "新版本", "热修"],
    "gacha.pull_rate": ["pull rate", "drop rate", "出率", "概率"],
    "gacha.pity": ["pity", "hard pity", "soft pity", "保底"],
    "gacha.banner": ["banner", "limited banner", "卡池", "限定池"],
    "gacha.currency": ["premium currency", "pull currency", "抽卡货币", "钻石"],
    "gacha.dupes": ["dupe", "duplicates", "constellation", "重复角色", "命座"],
    "gacha.power_creep": ["power creep", "数值膨胀", "强度膨胀"],
    "mmo.raid": ["raid", "raiding", "团本", "副本团"],
    "mmo.guild": ["guild", "公会"],
    "mmo.economy": ["auction house", "player economy", "交易行", "玩家经济"],
    "mmo.matchmaking": ["matchmaking", "queue time", "匹配", "排队"],
    "mmo.server_health": ["dead server", "server population", "服务器生态", "鬼服"],
    "simulation.sandbox_freedom": ["sandbox", "自由建造", "沙盒"],
    "simulation.system_depth": ["system depth", "deep simulation", "系统深度"],
    "simulation.customisation": ["customisation", "customization", "自定义"],
    "simulation.automation": ["automation", "自动化"],
    "fashion.wardrobe": ["wardrobe", "outfit", "衣橱", "服装", "穿搭"],
    "fashion.dye": ["dye", "colour palette", "染色", "配色"],
    "fashion.body_face": ["body shape", "face customisation", "捏脸", "体型"],
    "fashion.clipping": ["clipping", "穿模", "适配"],
}

POSITIVE_TERMS = ["love", "great", "good", "beautiful", "fun", "amazing", "enjoy", "smooth", "喜欢", "好玩", "漂亮", "优秀", "流畅", "惊喜", "不错"]
NEGATIVE_TERMS = ["hate", "bad", "worse", "boring", "broken", "awful", "terrible", "disappoint", "annoy", "frustrating", "垃圾", "无聊", "失望", "糟糕", "离谱", "劝退", "烦", "越来越烫"]
NEUTRAL_TERMS = ["average", "okay", "fine", "neutral", "一般", "还行", "中规中矩"]

BEHAVIOUR_RULES = {
    "churn_risk": ["stop playing", "quit the game", "uninstall", "won't log in", "not log in", "不想上线", "不太想上线", "退游", "卸载", "不玩了"],
    "return_intent": ["come back if", "return when", "play again if", "如果修好就回来", "修好会回坑"],
    "recommendation_intent": ["recommend this", "do not recommend", "don't recommend", "推荐", "不推荐", "劝退"],
    "payment_intent": ["willing to pay", "would buy", "will spend", "愿意付费", "会买", "会氪"],
    "payment_withdrawal": ["stop spending", "won't spend", "no more money", "不再氪", "不会再充", "再也不充", "不充了", "停止付费"],
    "frustration": ["frustrating", "fed up", "annoying", "烦死", "受不了", "太气了"],
    "bug_report": ["bug", "crash", "broken quest", "闪退", "崩溃", "任务卡住"],
}

REQUEST_PATTERNS = [
    r"\bplease\s+(?:add|fix|let|allow|make)\b",
    r"\b(?:i wish|we need|should add|needs an? option|could you)\b",
    r"(?:能不能|可不可以)(?:增加|加入|添加|修复|支持|允许|优化)?",
    r"(?:建议|请)(?:增加|加入|添加|修复|支持|允许|优化)",
    r"(?:我希望|希望能|希望可以|希望增加|希望加入|希望添加|希望修复|希望支持|希望允许|希望优化)",
]


def _normalise_tag(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "_", unicodedata.normalize("NFKC", value).casefold()).strip("_")


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _term_count(text: str, term: str) -> int:
    term = _normalise_text(term)
    if term.isascii() and re.search(r"[a-z]", term):
        return len(re.findall(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))
    return text.count(term)


def _contextual_topic_matches(text: str, topic_id: str) -> int:
    """Count context-sensitive topic cues that are unsafe as bare keywords."""

    if topic_id != "performance":
        return 0
    # Bare ``FPS`` often means the shooter genre ("FPS game" / "FPS 游戏"),
    # not frame-rate performance. Require a number or an explicit performance
    # modifier before treating it as a performance signal.
    patterns = [
        r"\b\d{1,3}\s*fps\b",
        r"\bfps\s*(?:drop(?:s|ped)?|dip(?:s|ped)?|low|unstable|issue|problem)\b",
        r"\bfps\s+(?:(?:is|feels|runs)\s+)?(?:terrible|bad|awful|great|smooth|unstable|low|high)\b",
        r"(?:只有|不到|低于|掉到|降到)\s*\d{1,3}\s*fps\b",
        r"\bfps\s*(?:很|太)?(?:低|高|差|不稳)\b",
    ]
    return sum(len(re.findall(pattern, text, flags=re.IGNORECASE)) for pattern in patterns)


def _sentences(text: str) -> list[str]:
    return [value.strip() for value in re.split(r"(?<=[.!?。！？])|[\r\n]+", text) if value.strip()]


def _sentiment(text: str) -> tuple[SentimentLabel, float | None, list[str]]:
    positive = [term for term in POSITIVE_TERMS if _term_count(text, term)]
    negative = [term for term in NEGATIVE_TERMS if _term_count(text, term)]
    neutral = [term for term in NEUTRAL_TERMS if _term_count(text, term)]
    if positive and negative:
        return SentimentLabel.MIXED, 0.0, [*positive[:3], *negative[:3]]
    if positive:
        return SentimentLabel.POSITIVE, min(1.0, 0.5 + 0.1 * len(positive)), positive[:4]
    if negative:
        return SentimentLabel.NEGATIVE, max(-1.0, -0.5 - 0.1 * len(negative)), negative[:4]
    if neutral:
        return SentimentLabel.NEUTRAL, 0.0, neutral[:4]
    return SentimentLabel.UNKNOWN, None, []


def _explicit_requests(original_text: str) -> list[str]:
    requests = []
    for sentence in _sentences(original_text):
        if any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in REQUEST_PATTERNS):
            requests.append(sentence[:300])
    return requests[:3]


def _behaviour_signals(text: str, explicit_requests: list[str], taxonomy: TaxonomyDefinition) -> list[str]:
    signals = [
        signal
        for signal, terms in BEHAVIOUR_RULES.items()
        if signal in taxonomy.behaviour_signal_ids and any(_term_count(text, term) for term in terms)
    ]
    if explicit_requests and "feature_request" in taxonomy.behaviour_signal_ids:
        signals.append("feature_request")
    return signals


def _pain_points(text: str, primary_topic: str, sentiment: SentimentLabel) -> list[str]:
    if sentiment not in {SentimentLabel.NEGATIVE, SentimentLabel.MIXED}:
        return []
    rules = [
        (["overheat", "heating", "发热", "越来越烫"], "device overheating"),
        (["fps drop", "frame drop", "掉帧", "帧率下降"], "frame-rate degradation"),
        (["stutter", "卡顿"], "stuttering"),
        (["crash", "闪退", "崩溃"], "crashes"),
        (["input lag", "输入延迟"], "input latency"),
        (["grind", "重复刷", "太肝"], "excessive repetition"),
        (["paywall", "逼氪", "付费墙"], "purchase pressure"),
    ]
    points = [label for terms, label in rules if any(_term_count(text, term) for term in terms)]
    if points and any(_term_count(text, term) for term in ["after update", "after the patch", "更新后", "新版本之后"]):
        points = [f"{value} after update" for value in points]
    if not points and primary_topic != "other_unclassified":
        negative_sentences = [
            sentence[:300]
            for sentence in _sentences(text)
            if any(_term_count(_normalise_text(sentence), term) for term in NEGATIVE_TERMS)
        ]
        points = negative_sentences[:1]
    return points[:3]


def _underlying_needs(primary_topic: str, pain_points: list[str]) -> list[str]:
    if not pain_points:
        return []
    if any(
        cue in point
        for point in pain_points
        for cue in ["overheating", "frame-rate", "stuttering", "crashes"]
    ):
        return ["stable and efficient performance"]
    needs = {
        "performance": "stable and efficient performance",
        "bugs_stability": "reliable, interruption-free play",
        "controls": "responsive and configurable controls",
        "ui_ux": "clear and low-friction interaction",
        "grind": "respectful progression pacing",
        "monetisation": "transparent and fair value",
        "gacha": "transparent and fair acquisition mechanics",
        "story": "coherent and engaging narrative delivery",
        "fair_play_integrity": "fair and trustworthy match integrity",
        "difficulty": "fair and learnable challenge",
        "account_service": "reliable account access and support",
    }
    return [needs[primary_topic]] if primary_topic in needs else []


def annotate_evidence(
    evidence: EvidenceItem,
    game: GameEntity,
    *,
    taxonomy: TaxonomyDefinition | None = None,
) -> AnalysisAnnotation:
    taxonomy = taxonomy or load_taxonomy()
    if evidence.game_id != game.game_id:
        raise ValueError("evidence and game identity do not match")
    text = _normalise_text(" ".join(value for value in [evidence.title or "", evidence.original_text] if value))
    active_topics = taxonomy.active_topic_ids(game)
    scores: dict[str, tuple[int, int]] = {}
    for topic_id in active_topics:
        terms = TOPIC_RULES.get(topic_id, [])
        contextual_matches = _contextual_topic_matches(text, topic_id)
        matches = sum(_term_count(text, term) for term in terms) + contextual_matches
        positions = [text.find(_normalise_text(term)) for term in terms if _term_count(text, term)]
        contextual_position = text.find("fps") if contextual_matches else -1
        first_position = min(
            (value for value in [*positions, contextual_position] if value >= 0),
            default=10**9,
        )
        if matches:
            scores[topic_id] = (matches, first_position)

    if scores:
        ordered = sorted(scores, key=lambda topic_id: (-scores[topic_id][0], scores[topic_id][1], topic_id))
        primary = ordered[0]
        primary_hits = scores[primary][0]
        secondary = [
            topic_id
            for topic_id in ordered[1:]
            if scores[topic_id][0] >= max(1, primary_hits // 2)
        ][:4]
    else:
        primary = taxonomy.unknown_topic
        secondary = []

    sentiment, sentiment_score, sentiment_terms = _sentiment(text)
    requests = _explicit_requests(evidence.original_text)
    behaviour = _behaviour_signals(text, requests, taxonomy)
    pain_points = _pain_points(text, primary, sentiment)
    needs = _underlying_needs(primary, pain_points)
    method_payload: dict[str, Any] = {
        "name": "transparent_bilingual_rules",
        "version": ANNOTATOR_VERSION,
        "taxonomy_config_hash": taxonomy.config_hash,
        "topic_scores": {topic_id: value[0] for topic_id, value in sorted(scores.items())},
        "sentiment_method": "bilingual_lexicon",
        "sentiment_terms": sentiment_terms,
        "source_native_recommendation_preserved": evidence.recommended is not None,
        "behaviour_semantics": "expressed_intent_not_observed_behaviour",
    }
    annotation_key = json.dumps(
        [evidence.evidence_id, taxonomy.version, ANNOTATOR_VERSION, taxonomy.config_hash],
        separators=(",", ":"),
    )
    return AnalysisAnnotation(
        annotation_id=f"annotation_{hashlib.sha256(annotation_key.encode('utf-8')).hexdigest()[:20]}",
        evidence_id=evidence.evidence_id,
        taxonomy_version=taxonomy.version,
        primary_topic=primary,
        secondary_topics=secondary,
        sentiment_label=sentiment,
        sentiment_score=sentiment_score,
        pain_points=pain_points,
        underlying_needs=needs,
        explicit_feature_requests=requests,
        behaviour_signals=behaviour,
        analysis_confidence=(0.35 if primary == taxonomy.unknown_topic else min(0.95, 0.55 + 0.08 * scores[primary][0])),
        method=method_payload,
        requires_human_review=(
            primary == taxonomy.unknown_topic
            or evidence.relevance_label.value != "relevant"
            or sentiment == SentimentLabel.UNKNOWN
        ),
    )


def annotate_corpus(
    evidence: Iterable[EvidenceItem],
    game: GameEntity,
    *,
    taxonomy: TaxonomyDefinition | None = None,
) -> list[AnalysisAnnotation]:
    taxonomy = taxonomy or load_taxonomy()
    return [annotate_evidence(item, game, taxonomy=taxonomy) for item in evidence]


def write_annotations_jsonl(annotations: Iterable[AnalysisAnnotation], output: Path) -> int:
    annotations = list(annotations)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for item in annotations),
        encoding="utf-8",
    )
    return len(annotations)


def priority_eligible_topic(topic_id: str, taxonomy: TaxonomyDefinition | None = None) -> bool:
    taxonomy = taxonomy or load_taxonomy()
    return topic_id != taxonomy.unknown_topic
