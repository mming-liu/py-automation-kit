"""批量文件重命名 / 信息提取。

典型场景：手机导出的照片、扫描件、合同 PDF、发票图片按日期归档。
安全策略：默认 dry-run 只出预览表，必须显式 --apply 才落盘，且执行前做冲突检测。
"""
from __future__ import annotations

import fnmatch
import re
from datetime import datetime
from pathlib import Path

DATE_PATTERNS = [
    (re.compile(r"(20\d{2})[-_.年]?(\d{1,2})[-_.月]?(\d{1,2})"), "filename"),
    (re.compile(r"(20\d{2})(\d{2})(\d{2})"), "filename"),
]


def extract_date(filename: str, mtime: float | None = None) -> tuple[str, str]:
    """从文件名提取日期，失败则回退到文件修改时间。

    返回 (YYYY-MM-DD, 来源)。来源取值：filename / mtime / unknown。
    """
    stem = Path(filename).stem
    for pattern, source in DATE_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        year, month, day = (int(g) for g in match.groups())
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d"), source
        except ValueError:
            continue  # 形如 20241345 的假日期，继续匹配下一规则
    if mtime is not None:
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"), "mtime"
    return "1970-01-01", "unknown"


def render_name(template: str, *, date: str, seq: int, name: str, ext: str, parent: str) -> str:
    """按模板渲染新文件名。模板占位符：{date} {seq} {seq:03d} {name} {ext} {parent}"""
    return template.format(date=date, seq=seq, name=name, ext=ext, parent=parent)


def build_plan(
    src_dir: str | Path,
    pattern: str = "*",
    template: str = "{date}_{seq:03d}{ext}",
    start: int = 1,
    recursive: bool = False,
    sort_by: str = "mtime",
) -> list[dict]:
    """生成重命名计划（不触碰磁盘）。

    sort_by: mtime 按修改时间 / name 按文件名 —— 决定序号顺序。
    """
    src = Path(src_dir)
    if not src.is_dir():
        raise NotADirectoryError(f"目录不存在：{src}")

    files = [p for p in (src.rglob("*") if recursive else src.glob("*")) if p.is_file()]
    files = [p for p in files if fnmatch.fnmatch(p.name, pattern)]
    if sort_by == "name":
        files.sort(key=lambda p: p.name.lower())
    else:
        files.sort(key=lambda p: (p.stat().st_mtime, p.name.lower()))

    plan: list[dict] = []
    for index, path in enumerate(files):
        stat = path.stat()
        date, date_source = extract_date(path.name, stat.st_mtime)
        new_name = render_name(
            template,
            date=date,
            seq=start + index,
            name=path.stem,
            ext=path.suffix.lower(),
            parent=path.parent.name,
        )
        plan.append(
            {
                "old_name": path.name,
                "new_name": new_name,
                "rel_dir": str(path.parent.relative_to(src)) if path.parent != src else ".",
                "date": date,
                "date_source": date_source,
                "size": stat.st_size,
            }
        )
    return plan


def check_plan(plan: list[dict], src_dir: str | Path) -> list[str]:
    """冲突检测：新文件名重复 / 目标已存在。返回问题列表（空表示可安全执行）。"""
    problems: list[str] = []
    seen: dict[tuple[str, str], int] = {}
    src = Path(src_dir)

    for item in plan:
        key = (item["rel_dir"], item["new_name"].lower())
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            problems.append(f"重名冲突：{item['rel_dir']}/{item['new_name']}（模板产出重复）")

        target = src / item["rel_dir"] / item["new_name"]
        if target.exists() and target.name != item["old_name"]:
            problems.append(f"目标已存在：{target}")

    return problems


def apply_plan(plan: list[dict], src_dir: str | Path) -> dict:
    """执行重命名。返回统计。调用前应先通过 check_plan。"""
    src = Path(src_dir)
    done, skipped = 0, 0
    for item in plan:
        if item["old_name"] == item["new_name"]:
            skipped += 1
            continue
        old = src / item["rel_dir"] / item["old_name"]
        new = src / item["rel_dir"] / item["new_name"]
        if not old.exists() or new.exists():
            skipped += 1
            continue
        old.rename(new)
        done += 1
    return {"renamed": done, "skipped": skipped}
