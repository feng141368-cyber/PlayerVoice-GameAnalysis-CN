#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gamepulse.analysis import analyze  # noqa: E402
from gamepulse.aliases import discover_aliases  # noqa: E402
from gamepulse.collection import collect  # noqa: E402
from gamepulse.collectors.community_export import collect_community_export  # noqa: E402
from gamepulse.config import load_config  # noqa: E402
from gamepulse.discovery import build_runtime_config  # noqa: E402
from gamepulse.foundation import FoundationResult, run_foundation_slice  # noqa: E402
from gamepulse.modes import ModeRequest, load_core_snapshot, route_mode  # noqa: E402
from gamepulse.modes.analyst import AnalystReport, render_analyst_markdown  # noqa: E402
from gamepulse.modes.compare import CompareReport, render_compare_markdown  # noqa: E402
from gamepulse.modes.creator import CreatorBrief, render_creator_markdown  # noqa: E402
from gamepulse.modes.player import PlayerReport, render_player_markdown  # noqa: E402
from gamepulse.query_builder import QueryBuilderSettings, build_query_plans  # noqa: E402
from gamepulse.report import create_chart, write_report  # noqa: E402
from gamepulse.resolver import resolve_game  # noqa: E402
from gamepulse.storage import save_raw_snapshot, upsert_csv  # noqa: E402
from gamepulse.voice_slice import run_voice_slice  # noqa: E402


def resolve_config(args: argparse.Namespace) -> dict:
    if getattr(args, "config", None):
        config = load_config(Path(args.config))
        if getattr(args, "game", None):
            config["project"]["game"] = args.game
        return config
    if not getattr(args, "game", None):
        raise SystemExit("Provide --game or --config")
    return build_runtime_config(args.game, steam_limit=getattr(args, "steam_limit", 500))


def command_collect(args: argparse.Namespace) -> dict:
    config = resolve_config(args)
    selected = set(args.sources.split(",")) if args.sources else None
    manifest = collect(config, ROOT, selected=selected, strict=args.strict, replace_game=args.fresh)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return config


def command_analyze(args: argparse.Namespace, config: dict | None = None) -> None:
    config = config or resolve_config(args)
    game = config["project"]["game"]
    slug = "".join(char.lower() if char.isalnum() else "-" for char in game).strip("-") or "game"
    output = ROOT / "reports" / slug
    result = analyze(
        ROOT / "data/processed/voice.csv",
        output,
        game,
        window_days=int(config.get("analysis", {}).get("window_days", 30)),
    )
    report_path = write_report(result, output)
    chart_path = create_chart(result, output)
    print(f"Report: {report_path.relative_to(ROOT)}")
    print(f"Chart: {chart_path.relative_to(ROOT)}")


def command_import(args: argparse.Namespace) -> None:
    rows = collect_community_export(args.game, Path(args.file), platform=args.platform)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = ROOT / "data/raw" / args.platform / f"{run_id}.jsonl"
    save_raw_snapshot(rows, snapshot)
    incoming, duplicates = upsert_csv(rows, ROOT / "data/processed/voice.csv")
    print(f"Imported {incoming} rows; replaced {duplicates} duplicate versions.")


def command_plan(args: argparse.Namespace) -> None:
    result = resolve_game(args.game, locale=args.locale)
    if result.status.value != "resolved" or result.game is None:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        raise SystemExit(2)
    aliases = discover_aliases(result.game)
    settings = QueryBuilderSettings(
        languages=[value.strip() for value in args.languages.split(",") if value.strip()],
        sources=[value.strip() for value in args.sources.split(",") if value.strip()],
        intents=[value.strip() for value in args.intents.split(",") if value.strip()],
        max_per_source_intent=args.max_per_source_intent,
    )
    plans = build_query_plans(result.game, aliases, run_id="run_preview", settings=settings)
    print(json.dumps([plan.to_dict() for plan in plans], ensure_ascii=False, indent=2))


def command_foundation(args: argparse.Namespace) -> None:
    result = run_foundation_slice(args.game, locale=args.locale)
    content = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(output)
    else:
        print(content, end="")


def command_voice_slice(args: argparse.Namespace) -> None:
    foundation = None
    if args.foundation:
        foundation = FoundationResult.model_validate_json(Path(args.foundation).read_text(encoding="utf-8"))
    output = Path(args.output)
    result = run_voice_slice(
        args.game,
        output,
        foundation=foundation,
        sources=[value.strip() for value in args.sources.split(",") if value.strip()],
        intents=[value.strip() for value in args.intents.split(",") if value.strip()],
        max_plans_per_source=args.max_plans_per_source,
        source_config={
            "steam": {"limit": args.items_per_query, "request_delay_seconds": args.request_delay_seconds},
            "bilibili": {
                "max_videos": 1,
                "comments_per_video": args.items_per_query,
                "request_delay_seconds": args.request_delay_seconds,
            },
        },
    )
    result_path = output / "voice_slice_result.json"
    result_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(result_path)


def command_mode(args: argparse.Namespace) -> None:
    contexts = [load_core_snapshot(Path(value)) for value in args.input_dir]
    preferences = args.preferences
    if args.preferences_file:
        preferences = Path(args.preferences_file).read_text(encoding="utf-8")
    request = ModeRequest(
        request_id=args.request_id,
        mode=args.mode,
        games=[context.game.game_id for context in contexts],
        languages=[value.strip() for value in args.languages.split(",") if value.strip()],
        preferences=preferences,
    )
    response = route_mode(request, contexts)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{args.mode}_mode.json"
    json_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    if args.mode == "player":
        report = PlayerReport.model_validate(response.payload)
        (output / "player_mode.md").write_text(
            render_player_markdown(report),
            encoding="utf-8",
        )
    elif args.mode == "creator":
        report = CreatorBrief.model_validate(response.payload)
        (output / "creator_brief.md").write_text(
            render_creator_markdown(report),
            encoding="utf-8",
        )
    elif args.mode == "analyst":
        report = AnalystReport.model_validate(response.payload)
        (output / "analyst_mode.md").write_text(
            render_analyst_markdown(report),
            encoding="utf-8",
        )
    elif args.mode == "compare":
        report = CompareReport.model_validate(response.payload)
        (output / "compare_mode.md").write_text(
            render_compare_markdown(
                report,
                {context.game.game_id: context.game.canonical_title for context in contexts},
            ),
            encoding="utf-8",
        )
    print(json_path)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Collect and analyze cross-platform game player voice")
    sub = root.add_subparsers(dest="command", required=True)
    for name in ["collect", "run"]:
        item = sub.add_parser(name)
        item.add_argument("--game")
        item.add_argument("--config")
        item.add_argument("--sources", help="Comma-separated subset: steam,bilibili,reddit,youtube,weibo,xiaohongshu,douyin")
        item.add_argument("--steam-limit", type=int, default=300)
        item.add_argument("--strict", action="store_true", help="Fail if any enabled source is unavailable")
        item.add_argument("--fresh", action="store_true", help="Replace existing rows for this game before saving")
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--game")
    analyze_parser.add_argument("--config")
    import_parser = sub.add_parser("import")
    import_parser.add_argument("--game", required=True)
    import_parser.add_argument("--platform", required=True, choices=["weibo", "xiaohongshu", "douyin", "discord", "other"])
    import_parser.add_argument("--file", required=True)
    discover = sub.add_parser("discover")
    discover.add_argument("--game", required=True)
    discover.add_argument("--steam-limit", type=int, default=300)
    plan = sub.add_parser("plan", help="Resolve a game and preview query plans without collecting")
    plan.add_argument("--game", required=True)
    plan.add_argument("--locale")
    plan.add_argument("--languages", default="zh-CN,en")
    plan.add_argument("--sources", default="official,steam,reddit,bilibili")
    plan.add_argument("--intents", default="general,performance,controls,patch")
    plan.add_argument("--max-per-source-intent", type=int, default=3)
    foundation = sub.add_parser("foundation", help="Run the Issue 1-5 foundation slice without UGC collection")
    foundation.add_argument("--game", required=True)
    foundation.add_argument("--locale")
    foundation.add_argument("--output")
    voice = sub.add_parser("voice-slice", help="Run the Issue 1-10 evidence-linked player voice slice")
    voice.add_argument("--game", required=True)
    voice.add_argument("--output", required=True)
    voice.add_argument("--foundation", help="Optional validated Issue 1-5 FoundationResult JSON fallback")
    voice.add_argument("--sources", default="steam,bilibili,reddit")
    voice.add_argument("--intents", default="general,performance,bugs,update")
    voice.add_argument("--max-plans-per-source", type=int, default=4)
    voice.add_argument("--items-per-query", type=int, default=20)
    voice.add_argument("--request-delay-seconds", type=float, default=0.6)
    mode = sub.add_parser("mode", help="Render an audience Mode from existing Intelligence Core output")
    mode.add_argument("--mode", required=True, choices=["player", "creator", "analyst", "compare"])
    mode.add_argument("--input-dir", action="append", required=True, help="Issue 10 output directory; repeat for Compare")
    mode.add_argument("--preferences")
    mode.add_argument("--preferences-file")
    mode.add_argument("--languages", default="zh-CN,en")
    mode.add_argument("--request-id", default="request_cli")
    mode.add_argument("--output", required=True)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "collect":
        command_collect(args)
    elif args.command == "analyze":
        command_analyze(args)
    elif args.command == "run":
        config = command_collect(args)
        command_analyze(args, config)
    elif args.command == "import":
        command_import(args)
    elif args.command == "discover":
        print(yaml.safe_dump(build_runtime_config(args.game, steam_limit=args.steam_limit), allow_unicode=True, sort_keys=False))
    elif args.command == "plan":
        command_plan(args)
    elif args.command == "foundation":
        command_foundation(args)
    elif args.command == "voice-slice":
        command_voice_slice(args)
    elif args.command == "mode":
        command_mode(args)


if __name__ == "__main__":
    main()
