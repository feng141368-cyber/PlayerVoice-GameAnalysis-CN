from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


TAXONOMY = {
    "Performance": ["crash", "lag", "frame", "fps", "stutter", "freeze", "loading", "disconnect", "optimi", "崩溃", "闪退", "卡顿", "掉帧", "发热", "加载", "断线", "优化"],
    "Monetization": ["price", "expensive", "gacha", "pity", "pull", "paywall", "currency", "top up", "价格", "氪", "抽卡", "保底", "付费", "充值", "礼包", "骗氪"],
    "Fashion/Customization": ["outfit", "fashion", "wardrobe", "dress", "dye", "customi", "cosmetic", "时装", "服装", "穿搭", "换装", "染色", "捏脸", "衣服"],
    "Combat/Balance": ["combat", "boss", "weapon", "dodge", "damage", "balance", "target", "战斗", "武器", "伤害", "平衡", "闪避", "boss", "强度"],
    "Story/Character": ["story", "character design", "character story", "plot", "dialogue", "voice acting", "companion", "romance", "剧情", "角色设计", "角色剧情", "文案", "配音", "陪伴", "好感", "恋爱"],
    "Content/Progression": ["content", "quest", "event", "map", "explor", "endgame", "grind", "任务", "活动", "地图", "探索", "长草", "肝", "养成"],
    "UI/UX": ["menu", "interface", "inventory", "control", "camera", "tutorial", "ui", "界面", "背包", "操作", "镜头", "引导", "按钮"],
    "Social/Community": ["guild", "coop", "co-op", "multiplayer", "server", "chat", "friend", "公会", "联机", "组队", "服务器", "聊天", "好友"],
    "Account/Service": ["lost my account", "account deleted", "account gone", "account wipe", "wiped my account", "data transfer", "migration", "transfer", "login", "account", "support", "ban", "customer service", "登录", "账号", "账户", "客服", "封号", "退款", "转移", "迁移", "数据没了"],
}

POSITIVE = ["love", "great", "good", "beautiful", "fun", "amazing", "enjoy", "better", "喜欢", "好玩", "漂亮", "优秀", "惊喜", "良心", "爱了", "不错"]
NEGATIVE = ["hate", "bad", "worse", "boring", "broken", "awful", "terrible", "disappoint", "annoy", "垃圾", "无聊", "失望", "恶心", "难受", "糟糕", "离谱", "劝退"]


def classify_topic(text: str) -> tuple[str, int]:
    normalized = re.sub(r"\s+", " ", str(text).casefold())
    def occurrences(term: str) -> int:
        if term.isascii() and re.search(r"[a-z]", term):
            return len(re.findall(rf"(?<![a-z]){re.escape(term)}(?![a-z])", normalized))
        return normalized.count(term)
    scores = {topic: sum(occurrences(term) for term in terms) for topic, terms in TAXONOMY.items()}
    topic, hits = max(scores.items(), key=lambda item: item[1])
    return (topic, hits) if hits else ("Other", 0)


def lexical_sentiment(text: str) -> float:
    normalized = str(text).casefold()
    positive = sum(normalized.count(term) for term in POSITIVE)
    negative = sum(normalized.count(term) for term in NEGATIVE)
    total = positive + negative
    return 0.0 if total == 0 else (positive - negative) / total


def _bool_or_none(value: Any) -> bool | None:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _score_bucket(value: float, thresholds: tuple[float, float, float]) -> int:
    return 3 if value >= thresholds[2] else 2 if value >= thresholds[1] else 1 if value >= thresholds[0] else 0


def analyze(dataset: Path, output_dir: Path, game: str, window_days: int = 30) -> dict[str, Any]:
    frame = pd.read_csv(dataset)
    frame = frame[frame.game.str.casefold() == game.casefold()].copy()
    if frame.empty:
        raise ValueError(f"No collected records found for game: {game}")
    frame["created_at"] = pd.to_datetime(frame.created_at, utc=True, errors="coerce")
    frame = frame.dropna(subset=["created_at", "text"])
    classified = frame.text.map(classify_topic)
    frame["topic"] = classified.map(lambda item: item[0])
    frame["topic_hits"] = classified.map(lambda item: item[1])
    frame["sentiment_score"] = frame.text.map(lexical_sentiment)
    frame["native_recommended"] = frame.recommended.map(_bool_or_none)
    frame["is_negative"] = frame.apply(
        lambda row: (not row.native_recommended) if row.native_recommended is not None else row.sentiment_score < 0,
        axis=1,
    )
    frame["engagement_score"] = pd.to_numeric(frame.engagement_score, errors="coerce").fillna(0).clip(lower=0)
    frame["engagement_weight"] = frame.engagement_score.map(lambda value: 1 + math.log1p(value))

    anchor = frame.created_at.max()
    recent_start = anchor - pd.Timedelta(days=window_days)
    prior_start = recent_start - pd.Timedelta(days=window_days)
    frame["period"] = "older"
    frame.loc[(frame.created_at >= prior_start) & (frame.created_at < recent_start), "period"] = "prior"
    frame.loc[frame.created_at >= recent_start, "period"] = "recent"

    source_summary = (
        frame.groupby("source", as_index=False)
        .agg(records=("record_id", "count"), earliest=("created_at", "min"), latest=("created_at", "max"),
             negative_share=("is_negative", "mean"), engagement=("engagement_score", "sum"))
        .sort_values("records", ascending=False)
    )
    topic_source = (
        frame.groupby(["topic", "source"], as_index=False)
        .agg(records=("record_id", "count"), negative_share=("is_negative", "mean"), engagement=("engagement_score", "sum"))
    )

    topic_rows = []
    max_volume = max(1, int(frame.groupby("topic").size().max()))
    for topic, group in frame.groupby("topic"):
        recent = int((group.period == "recent").sum())
        prior = int((group.period == "prior").sum())
        recent_total = max(1, int((frame.period == "recent").sum()))
        prior_total = max(1, int((frame.period == "prior").sum()))
        recent_share = recent / recent_total
        prior_share = prior / prior_total
        momentum = (recent_share + 0.005) / (prior_share + 0.005)
        volume = len(group)
        negative_share = float(group.is_negative.mean())
        source_count = int(group.source.nunique())
        volume_score = _score_bucket(volume / max_volume, (0.15, 0.35, 0.65))
        negativity_score = _score_bucket(negative_share, (0.20, 0.40, 0.60))
        momentum_score = _score_bucket(momentum, (1.05, 1.30, 1.75)) if recent + prior >= 5 else 0
        breadth_score = min(3, source_count)
        total = volume_score + negativity_score + momentum_score + breadth_score
        if topic == "Other":
            total, label = 0, "N/A"
        else:
            label = "P0" if total >= 10 else "P1" if total >= 7 else "P2" if total >= 4 else "P3"
        topic_rows.append(
            {"topic": topic, "records": volume, "share": volume / len(frame), "negative_share": negative_share,
             "sources": source_count, "recent_records": recent, "prior_records": prior, "momentum": momentum,
             "volume_score": volume_score, "negativity_score": negativity_score,
             "momentum_score": momentum_score, "breadth_score": breadth_score,
             "priority_score": total, "priority": label}
        )
    topic_summary = pd.DataFrame(topic_rows).sort_values(["priority_score", "records"], ascending=False)

    excerpts: dict[str, list[dict[str, Any]]] = {}
    for topic in topic_summary.head(6).topic:
        candidates = frame[(frame.topic == topic) & frame.is_negative].sort_values(
            ["engagement_score", "created_at"], ascending=False
        ).head(3)
        excerpts[topic] = [
            {"source": row.source, "created_at": row.created_at.isoformat(), "text": str(row.text)[:280],
             "url": row.url if isinstance(row.url, str) else None, "engagement": int(row.engagement_score)}
            for row in candidates.itertuples(index=False)
        ]

    output_dir.mkdir(parents=True, exist_ok=True)
    annotated_path = output_dir / "voice_annotated.csv"
    frame.to_csv(annotated_path, index=False)
    source_summary.to_csv(output_dir / "source_summary.csv", index=False)
    topic_source.to_csv(output_dir / "topic_by_source.csv", index=False)
    topic_summary.to_csv(output_dir / "topic_priority.csv", index=False)
    return {
        "game": game,
        "records": len(frame),
        "sources": int(frame.source.nunique()),
        "anchor_date": anchor.isoformat(),
        "window_days": window_days,
        "source_summary": source_summary,
        "topic_source": topic_source,
        "topic_summary": topic_summary,
        "excerpts": excerpts,
    }
