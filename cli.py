"""py-automation-kit 统一命令行入口。

用法：
    python cli.py demo                                    一键跑完整演示
    python cli.py rename --dir workspace/inbox --apply     批量重命名
    python cli.py merge                                   合并多表
    python cli.py split                                   按列拆表
    python cli.py api                                     接口对接同步
    python cli.py report                                  生成运行日报
    python cli.py selftest                                执行自测用例
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kit import api_sync, rename_batch, report_daily, sheet_ops  # noqa: E402
from kit.common import ensure_dir, get_logger, setup_console, write_csv, write_text  # noqa: E402

LOG = get_logger("kit")
WS = ROOT / "workspace"


def _save_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------ 各子任务
def cmd_rename(args) -> dict:
    plan = rename_batch.build_plan(
        args.dir,
        pattern=args.pattern,
        template=args.template,
        start=args.start,
        recursive=args.recursive,
        sort_by=args.sort_by,
    )
    plan_out = Path(args.out) if args.out else WS / "out" / "rename_plan.csv"
    write_csv(plan_out, ["old_name", "new_name", "rel_dir", "date", "date_source", "size"], plan)

    problems = rename_batch.check_plan(plan, args.dir)
    for problem in problems:
        LOG.warning(problem)

    result = {"files": len(plan), "conflicts": len(problems), "preview": str(plan_out), "applied": False}
    if args.apply:
        if problems:
            raise SystemExit("存在命名冲突，已中止执行。请调整模板后重试。")
        result.update(rename_batch.apply_plan(plan, args.dir))
        result["applied"] = True
    return result


def cmd_merge(args) -> dict:
    inputs = args.inputs or sorted((WS / "raw").glob("*.csv"))
    result = sheet_ops.merge_csv(
        inputs,
        args.out,
        source_column=args.source_column,
        add_source=not args.no_source,
        dedupe_key=args.dedupe,
    )
    _save_json(WS / "out" / "merge_stats.json", {k: v for k, v in result.items() if k != "per_file"})
    return result


def cmd_split(args) -> dict:
    result = sheet_ops.split_csv(args.input, args.out_dir, args.by, prefix=args.prefix)
    _save_json(WS / "out" / "split_stats.json", {"groups": result["groups"], "rows": result["rows"]})
    return result


def cmd_api(args) -> dict:
    out_csv = Path(args.out)
    with api_sync.MockServer(total=args.total, fail_first_hit=not args.no_fault) as server:
        LOG.info("本地 Mock 接口已启动：%s", server.base_url)
        stats = api_sync.sync_orders(
            server.base_url,
            out_csv,
            log_path=WS / "out" / "api_sync.log",
            page_size=args.page_size,
        )
    _save_json(WS / "out" / "api_sync_stats.json", stats)
    return stats


def cmd_report(args) -> dict:
    md_path = report_daily.build_report(WS, title=args.title)
    html_path = report_daily.build_html_report(WS, title=args.title)
    return {"report": str(md_path), "html": str(html_path)}


def cmd_demo(args) -> None:
    LOG.info("Step 1/5 生成演示数据")
    from demo.make_demo_data import make_all

    info = make_all(WS)
    LOG.info("  造出 %d 个命名混乱的文件，3 份表头不一致的门店报表", info["inbox_files"])

    LOG.info("Step 2/5 批量重命名（先预览、无冲突再落盘）")
    ns = argparse.Namespace(
        dir=str(WS / "inbox"),
        pattern="*",
        template="{date}_{seq:03d}{ext}",
        start=1,
        recursive=True,
        sort_by="mtime",
        out=str(WS / "out" / "rename_plan.csv"),
        apply=True,
    )
    res = cmd_rename(ns)
    _save_json(WS / "out" / "rename_stats.json", {"files": res["files"], "renamed": res.get("renamed", 0), "conflicts": res["conflicts"]})
    LOG.info("  重命名 %d 个文件，冲突 %d 个（预览表已存 out/rename_plan.csv）", res.get("renamed", 0), res["conflicts"])

    LOG.info("Step 3/5 合并三份门店报表（表头不一致自动对齐）")
    res = cmd_merge(
        argparse.Namespace(
            inputs=sorted((WS / "raw").glob("sales_*.csv")),
            out=str(WS / "out" / "merged_sales.csv"),
            source_column="来源文件",
            no_source=False,
            dedupe=None,
        )
    )
    LOG.info("  %d 份 → %d 行 / %d 列，输出 out/merged_sales.csv", res["files"], res["rows_out"], res["columns"])

    LOG.info("Step 4/5 接口分页同步（含首次失败重试）")
    res = cmd_api(
        argparse.Namespace(
            out=str(WS / "out" / "orders_synced.csv"),
            total=137,
            page_size=25,
            no_fault=False,
        )
    )
    LOG.info("  拉取 %d 行 / %d 页，重试 %d 次，耗时 %.2fs", res["rows"], res["pages"], res["retries"], res["elapsed_s"])

    LOG.info("Step 5/5 生成运行日报")
    res = cmd_report(argparse.Namespace(title="办公自动化批处理日报"))
    LOG.info("  日报已生成：%s", res["report"])


def cmd_selftest(args) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"],
        cwd=str(ROOT),
    )
    return proc.returncode


# ------------------------------------------------------------------ 入口
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py-automation-kit",
        description="本地 Python 自动化脚本工具箱 —— 批量重命名 / 表格合并拆分 / 接口同步 / 日报生成",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="一键跑完整演示流程")
    p_demo.set_defaults(func=cmd_demo)

    p_rename = sub.add_parser("rename", help="批量重命名（默认 dry-run 只出预览）")
    p_rename.add_argument("--dir", default=str(WS / "inbox"))
    p_rename.add_argument("--pattern", default="*", help="文件过滤，如 *.jpg")
    p_rename.add_argument("--template", default="{date}_{seq:03d}{ext}", help="占位符：{date} {seq} {name} {ext} {parent}")
    p_rename.add_argument("--start", type=int, default=1)
    p_rename.add_argument("--recursive", action="store_true", help="包含子目录")
    p_rename.add_argument("--sort-by", choices=["mtime", "name"], default="mtime")
    p_rename.add_argument("--out", default=None, help="预览表路径")
    p_rename.add_argument("--apply", action="store_true", help="真正执行（不加则只预览）")
    p_rename.set_defaults(func=cmd_rename)

    p_merge = sub.add_parser("merge", help="合并多个 CSV")
    p_merge.add_argument("--inputs", nargs="*", default=None, help="默认取 workspace/raw/*.csv")
    p_merge.add_argument("--out", default=str(WS / "out" / "merged.csv"))
    p_merge.add_argument("--source-column", default="来源文件")
    p_merge.add_argument("--no-source", action="store_true", help="不追加来源列")
    p_merge.add_argument("--dedupe", default=None, help="按指定列去重")
    p_merge.set_defaults(func=cmd_merge)

    p_split = sub.add_parser("split", help="按列拆分为多个 CSV")
    p_split.add_argument("--input", default=str(WS / "raw" / "orders_raw.csv"))
    p_split.add_argument("--by", default="region")
    p_split.add_argument("--out-dir", default=str(WS / "out" / "parts"))
    p_split.add_argument("--prefix", default="part")
    p_split.set_defaults(func=cmd_split)

    p_api = sub.add_parser("api", help="接口分页同步（内置离线 Mock 服务）")
    p_api.add_argument("--out", default=str(WS / "out" / "orders_synced.csv"))
    p_api.add_argument("--total", type=int, default=137)
    p_api.add_argument("--page-size", type=int, default=25)
    p_api.add_argument("--no-fault", action="store_true", help="关闭模拟抖动")
    p_api.set_defaults(func=cmd_api)

    p_report = sub.add_parser("report", help="生成 Markdown 运行日报")
    p_report.add_argument("--title", default="自动化批处理日报")
    p_report.set_defaults(func=cmd_report)

    p_test = sub.add_parser("selftest", help="执行自测用例")
    p_test.set_defaults(func=cmd_selftest)

    return parser


def main(argv: list[str] | None = None) -> int:
    setup_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "selftest":
        code = cmd_selftest(args)
        LOG.info("自测结束，退出码 %d", code)
        return code

    result = args.func(args)
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
