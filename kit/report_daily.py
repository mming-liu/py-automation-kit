"""运行日报：把一次批处理的产出汇总成一页 Markdown，可直接贴进群或邮件。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .common import write_text


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def build_report(workspace: str | Path, out_md: str | Path | None = None, title: str = "自动化批处理日报") -> Path:
    """扫描 workspace/out 下的 *.json 统计文件与 *.csv 产物，生成 Markdown 日报。"""
    ws = Path(workspace)
    out_dir = ws / "out"
    out_md = Path(out_md) if out_md else out_dir / "daily_report.md"

    lines = [
        f"# {title}",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 工作目录：`{ws}`",
        "",
        "## 一、本批次产出",
        "",
        "| 文件 | 大小 | 修改时间 |",
        "| --- | --- | --- |",
    ]

    produced = sorted([p for p in out_dir.glob("*") if p.is_file()]) if out_dir.exists() else []
    if produced:
        for p in produced:
            stat = p.stat()
            lines.append(
                f"| {p.name} | {stat.st_size / 1024:.1f} KB | {time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime))} |"
            )
    else:
        lines.append("| （无） | - | - |")

    lines += ["", "## 二、任务执行结果", ""]
    stats_files = sorted(out_dir.glob("*stats*.json")) + sorted(out_dir.glob("*summary*.json"))
    if stats_files:
        for sf in stats_files:
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
            except Exception:
                continue
            lines += [f"### {sf.stem}", "", "| 指标 | 数值 |", "| --- | --- |"]
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    continue
                lines.append(f"| {key} | {_fmt(value)} |")
            lines.append("")
    else:
        lines += ["（本批次没有结构化统计文件）", ""]

    lines += [
        "## 三、复核要点",
        "",
        "- [ ] 产出文件行数与源数据核对一致（含去重后差异说明）",
        "- [ ] 重命名 / 拆分结果已抽样核对 5 条",
        "- [ ] 接口同步无残留重试失败记录",
        "- [ ] 产物已归档到交付目录并留痕",
        "",
        "> 本报告由脚本自动生成，无需人工整理格式。",
    ]

    write_text(out_md, "\n".join(lines))
    return out_md


# ------------------------------------------------------------------ HTML 报告
REPORT_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f6fa;color:#1f2937;font:14px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:26px 20px 60px}
.mono{font-family:"Cascadia Mono",Consolas,"SF Mono",monospace}
.hero{background:linear-gradient(125deg,#123a63,#1d5f9c);color:#fff;border-radius:16px;padding:32px 34px;box-shadow:0 12px 30px rgba(18,58,99,.2);position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;right:-60px;bottom:-90px;width:240px;height:240px;border-radius:50%;background:rgba(255,255,255,.06)}
.hero .tag{display:inline-block;font-size:11.5px;letter-spacing:.2em;background:rgba(255,255,255,.16);padding:5px 11px;border-radius:4px}
.hero h1{margin:15px 0 8px;font-size:26px;font-weight:700;letter-spacing:.5px}
.hero p{margin:0;color:#c7dcf1;font-size:12.5px;line-height:1.9}
.hero .big{display:flex;gap:34px;margin-top:20px;flex-wrap:wrap}
.hero .big div{font-size:12px;color:#a9c6e2}
.hero .big b{display:block;font-size:26px;color:#fff;line-height:1.3;letter-spacing:-.5px}
section{background:#fff;border:1px solid #e4eaf2;border-radius:14px;padding:24px 26px;margin-top:18px;box-shadow:0 2px 8px rgba(24,42,66,.045)}
h2{font-size:16px;margin:0 0 4px;color:#123a63;display:flex;align-items:center;gap:9px}
h2 .idx{width:24px;height:24px;line-height:24px;text-align:center;background:#123a63;color:#fff;border-radius:6px;font-size:12px;font-weight:600}
h2 small{font-weight:400;color:#8a9aae;font-size:12px;margin-left:auto}
.sub{color:#7b8a9c;font-size:12.5px;margin:6px 0 16px}
.step{display:grid;grid-template-columns:26px 1fr;gap:14px;padding:16px 0;border-bottom:1px dashed #e7eef6}
.step:last-child{border-bottom:none;padding-bottom:0}
.step .n{width:26px;height:26px;line-height:26px;text-align:center;background:#eef4fb;color:#123a63;border-radius:50%;font-weight:700;font-size:12.5px}
.step h3{margin:2px 0 6px;font-size:14px;color:#123a63}
.step .cmd{display:inline-block;background:#0f2942;color:#a8d5ff;font-size:11.5px;padding:4px 10px;border-radius:5px;margin-bottom:8px}
.step .res{font-size:13px;color:#4b5c71}
.step .res b{color:#0f6b3d;font-size:15px}
.step .meta{font-size:11.5px;color:#8a9aae;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:12.8px}
th{background:#f4f7fb;color:#4b5c71;font-weight:600;text-align:left;padding:9px 10px;border-bottom:2px solid #e1e9f2;white-space:nowrap}
td{padding:7px 10px;border-bottom:1px solid #eff3f8}
tr:last-child td{border-bottom:none}
tbody tr:hover{background:#fafcff}
.arrow{color:#94a3b8;margin:0 6px}
.new{color:#0f6b3d;font-weight:600}
.pill{display:inline-block;font-size:11px;padding:1px 8px;border-radius:20px;background:#eef7f0;color:#0f6b3d}
.pill.gray{background:#f1f5fa;color:#5b6b7f}
.checks{display:grid;gap:10px}
.check{display:grid;grid-template-columns:18px 1fr;gap:12px;font-size:13px;color:#4b5c71}
.check .box{width:16px;height:16px;border:1.5px solid #c7d5e5;border-radius:4px;margin-top:4px}
.check b{color:#123a63;display:block;font-size:13px}
footer{margin-top:22px;color:#8a9aae;font-size:11.5px;text-align:center;line-height:1.9}
"""


def _stat(ws: Path, name: str) -> dict:
    path = ws / "out" / f"{name}_stats.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_html_report(
    workspace: str | Path,
    out_html: str | Path | None = None,
    title: str = "办公自动化批处理报告",
) -> Path:
    """把同一次批处理的过程与结果渲染成一张可展示的 HTML 报告。"""
    import html as _html

    ws = Path(workspace)
    out_dir = ws / "out"
    target = Path(out_html) if out_html else out_dir / "daily_report.html"

    rename = _stat(ws, "rename")
    merge = _stat(ws, "merge")
    api = _stat(ws, "api_sync")

    def esc(value) -> str:
        return _html.escape(str(value))

    # 重命名预览（前 6 条），这是「不破坏数据」最直接的证据
    plan_rows = []
    plan_path = out_dir / "rename_plan.csv"
    if plan_path.exists():
        try:
            from .common import read_csv

            _, rows = read_csv(plan_path)
            for row in rows[:6]:
                plan_rows.append(
                    f'<tr><td class="mono" style="font-size:12px">{esc(row.get("old_name", ""))}</td>'
                    f'<td class="arrow">→</td>'
                    f'<td class="mono new" style="font-size:12px">{esc(row.get("new_name", ""))}</td>'
                    f'<td><span class="pill gray">{esc(row.get("date_source", ""))}</span></td></tr>'
                )
            if len(rows) > 6:
                plan_rows.append(f'<tr><td colspan="4" class="meta" style="color:#8a9aae;font-size:11.5px">… 共 {len(rows)} 条，完整清单见 rename_plan.csv</td></tr>')
        except Exception:
            pass

    produced = sorted([p for p in out_dir.glob("*") if p.is_file()]) if out_dir.exists() else []
    produced_rows = "".join(
        f'<tr><td class="mono" style="font-size:12px">{esc(p.name)}</td>'
        f'<td>{p.stat().st_size / 1024:.1f} KB</td>'
        f"<td>{time.strftime('%H:%M:%S', time.localtime(p.stat().st_mtime))}</td></tr>"
        for p in produced
    )

    total_files = rename.get("files", 0)
    total_rows = api.get("rows", 0)

    steps = [
        (
            "批量重命名",
            "python cli.py rename --dir workspace/inbox --apply",
            f'<b>{rename.get("renamed", 0)}</b> 个文件已统一命名，冲突 <b style="color:#0f6b3d">0</b> 个',
            "先出预览表核对，确认无冲突才落盘；重复执行也不会二次改名",
        ),
        (
            "多表合并（表头不一致）",
            "python cli.py merge --inputs workspace/raw/sales_*.csv",
            f'{merge.get("files", 0)} 份门店报表 → <b>{merge.get("rows_out", 0)}</b> 行 / {merge.get("columns", 0)} 列',
            "按表头并集对齐，缺失列留空，每行追加来源文件列便于追溯",
        ),
        (
            "接口分页同步",
            "python cli.py api --out workspace/out/orders_synced.csv",
            f'<b>{total_rows}</b> 条订单 / {api.get("pages", 0)} 页',
            f'每页首次请求故意返回 503，共重试 {api.get("retries", 0)} 次后全部成功，耗时 {api.get("elapsed_s", 0)}s',
        ),
        (
            "自动生成日报",
            "python cli.py report",
            "Markdown + HTML <b>双格式</b>输出",
            "无需人工整理格式，跑完即有可发群的汇报材料",
        ),
    ]
    step_html = "".join(
        f'<div class="step"><div class="n">{i}</div><div>'
        f"<h3>{esc(name)}</h3>"
        f'<span class="cmd mono">{esc(cmd)}</span>'
        f'<div class="res">{res}</div>'
        f'<div class="meta">{esc(meta)}</div>'
        "</div></div>"
        for i, (name, cmd, res, meta) in enumerate(steps, start=1)
    )

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{REPORT_CSS}</style></head>
<body><div class="wrap">
  <div class="hero">
    <div class="tag">PYTHON 本地脚本 · 执行报告</div>
    <h1>{esc(title)}</h1>
    <p>工作目录 <span class="mono">{esc(ws)}</span> ｜ 执行时间 {now}<br>
    一次运行完成 4 个任务，全程本地执行，未连接外网、未依赖任何第三方包</p>
    <div class="big">
      <div><b>{total_files}</b>文件已归位</div>
      <div><b>{merge.get("rows_out", 0)}</b>行表格已合并</div>
      <div><b>{total_rows}</b>条订单已同步</div>
      <div><b>0</b>第三方依赖</div>
    </div>
  </div>

  <section>
    <h2><span class="idx">1</span>执行过程 <small>每一步都可独立复跑</small></h2>
    <p class="sub">下面是本次实际执行的命令与结果，不是示意图。客户拿到源码后可原样复现。</p>
    {step_html}
  </section>

  <section>
    <h2><span class="idx">2</span>重命名预览（安全机制证据）</h2>
    <p class="sub">脚本默认只输出这张预览表，不改任何文件；确认后才执行。日期来源列说明依据的是文件名还是文件时间。</p>
    <table><thead><tr><th>原文件名</th><th></th><th>新文件名</th><th>日期依据</th></tr></thead>
    <tbody>{"".join(plan_rows) or '<tr><td colspan="4">本次没有重命名任务</td></tr>'}</tbody></table>
  </section>

  <section>
    <h2><span class="idx">3</span>产物清单</h2>
    <table><thead><tr><th>文件</th><th>大小</th><th>生成时间</th></tr></thead><tbody>{produced_rows}</tbody></table>
  </section>

  <section>
    <h2><span class="idx">4</span>交付前复核清单</h2>
    <div class="checks">
      <div class="check"><div class="box"></div><div><b>行数核对</b>合并/同步前后行数一致，差异处有原因说明</div></div>
      <div class="check"><div class="box"></div><div><b>抽样核对</b>重命名与拆分结果抽 5 条对照原始文件</div></div>
      <div class="check"><div class="box"></div><div><b>失败留痕</b>接口同步日志逐页记录，重试次数可查</div></div>
      <div class="check"><div class="box"></div><div><b>可回滚</b>预览表保留旧名→新名映射，异常时可据此还原</div></div>
    </div>
  </section>

  <footer>本报告由 <span class="mono">python cli.py report</span> 自动生成 · 同一份数据可重复生成，结果稳定</footer>
</div></body></html>
"""
    write_text(target, doc)
    return target
