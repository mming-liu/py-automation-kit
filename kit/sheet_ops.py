"""表格合并 / 拆分。

合并：多个 CSV 表头不一致时按并集对齐，缺失列留空，并追加来源列，可追溯到原始文件。
拆分：按指定列分组写出多个文件，用于分区域 / 分渠道下发给不同同事。
"""
from __future__ import annotations

import csv
from pathlib import Path

from .common import ensure_dir, read_csv, write_csv


def merge_csv(
    inputs: list[str | Path],
    out_path: str | Path,
    source_column: str = "来源文件",
    add_source: bool = True,
    dedupe_key: str | None = None,
) -> dict:
    """合并多个 CSV。

    inputs       : 待合并文件列表（可混合不同表头）
    dedupe_key   : 指定列作为去重键，重复行只保留首次出现
    返回统计字典。
    """
    if not inputs:
        raise ValueError("没有待合并的文件")

    header: list[str] = []
    merged: list[dict] = []
    per_file: dict[str, int] = {}

    for path in inputs:
        path = Path(path)
        cols, rows = read_csv(path)
        for col in cols:
            if col not in header:
                header.append(col)
        per_file[path.name] = len(rows)
        for row in rows:
            if add_source:
                row[source_column] = path.name
            merged.append(row)

    dropped = 0
    if dedupe_key:
        seen: set[str] = set()
        unique: list[dict] = []
        for row in merged:
            key = (row.get(dedupe_key) or "").strip()
            if key and key in seen:
                dropped += 1
                continue
            seen.add(key)
            unique.append(row)
        merged = unique

    if add_source and source_column not in header:
        header.append(source_column)

    write_csv(out_path, header, merged)
    return {
        "files": len(inputs),
        "rows_in": sum(per_file.values()),
        "rows_out": len(merged),
        "deduped": dropped,
        "columns": len(header),
        "per_file": per_file,
        "output": str(out_path),
    }


def split_csv(
    input_path: str | Path,
    out_dir: str | Path,
    by_column: str,
    prefix: str = "part",
    encoding: str = "utf-8-sig",
) -> dict:
    """按某一列分组拆分 CSV，每组写一个文件。"""
    header, rows = read_csv(input_path)
    if by_column not in header:
        raise KeyError(f"列 {by_column} 不存在，可选列：{', '.join(header)}")

    buckets: dict[str, list[dict]] = {}
    blank_key = "_未填写"
    for row in rows:
        key = (row.get(by_column) or "").strip() or blank_key
        buckets.setdefault(key, []).append(row)

    target_dir = ensure_dir(out_dir)
    written: dict[str, str] = {}
    for key, group in sorted(buckets.items()):
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        path = target_dir / f"{prefix}_{safe}.csv"
        write_csv(path, header, group, encoding=encoding)
        written[key] = f"{path.name} ({len(group)} 行)"

    return {"groups": len(buckets), "rows": len(rows), "files": written, "output_dir": str(target_dir)}


def head_csv(path: str | Path, limit: int = 10) -> list[dict]:
    """预览前 N 行。"""
    _, rows = read_csv(path)
    return rows[:limit]


def describe_csv(path: str | Path) -> dict:
    """快速体检：行列数、字段名、空值率。"""
    header, rows = read_csv(path)
    total = len(rows) or 1
    blanks = {col: round(sum(1 for r in rows if not (r.get(col) or "").strip()) / total * 100, 1) for col in header}
    return {"rows": len(rows), "columns": len(header), "header": header, "blank_rate_pct": blanks}
