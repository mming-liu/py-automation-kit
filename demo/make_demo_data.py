"""生成演示数据：一批命名混乱的文件 + 三个表头不一致的 CSV。

可重复执行：每次运行会先清空 workspace 下的演示目录再重建，保证演示结果稳定。
"""
from __future__ import annotations

import os
import random
import shutil
import time
from pathlib import Path

MESSY_FILES = [
    "IMG_20240715_093012.jpg",
    "IMG_20240715_093105.jpg",
    "IMG_20240716_141230.jpg",
    "微信图片_20240803.jpg",
    "微信图片_20240803(1).jpg",
    "扫描件2024-08-12.pdf",
    "扫描件2024-08-12 (1).pdf",
    "合同_20240912_扫描.pdf",
    "合同20240912补充协议.pdf",
    "发票20241005.pdf",
    "发票 20241005.pdf",
    "报价单_20241018.xlsx",
    "对账单20241108.xlsx",
    "photo.jpg",
    "photo(1).jpg",
    "截图 2024-11-21.png",
    "新建文件夹/IMG_20241203_101010.jpg",
    "新建文件夹/IMG_20241203_101155.jpg",
    "新建文件夹/12月盘点表20241215.xlsx",
]

REGIONS = ["华东", "华北", "华南"]
CHANNELS = ["官网", "天猫", "京东"]


def _touch_files(root: Path) -> int:
    count = 0
    base_time = time.time() - 40 * 86400
    for index, name in enumerate(MESSY_FILES):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # 写一点真实字节，让体积统计不全是 0
        path.write_bytes(os.urandom(random.randint(800, 6000)))
        if "photo" in name or name == "截图 2024-11-21.png":
            # 这两类文件名里没有日期，用修改时间来兜底，演示 fallback 逻辑
            ts = base_time + index * 3600
            os.utime(path, (ts, ts))
        count += 1
    return count


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _make_split_csv(root: Path) -> Path:
    rng = random.Random(7)
    rows = []
    for i in range(1, 91):
        region = REGIONS[i % 3]
        channel = CHANNELS[i % 3]
        qty = rng.randint(1, 20)
        price = round(rng.uniform(20, 400), 2)
        rows.append(
            [f"SO2026{i:05d}", f"2026-09-{rng.randint(1, 28):02d}", region, channel, qty, price, round(qty * price, 2)]
        )
    path = root / "orders_raw.csv"
    _write_csv(path, ["order_id", "order_date", "region", "channel", "qty", "unit_price", "amount"], rows)
    return path


def make_rename_samples(workspace: str | Path) -> dict:
    """只生成「批量重命名」的样例：19 个命名混乱的文件（不清空 out/）。"""
    ws = Path(workspace)
    inbox = ws / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    count = _touch_files(inbox)
    return {"inbox_files": count, "inbox_dir": str(inbox)}


def make_merge_samples(workspace: str | Path) -> dict:
    """只生成「多表合并」的样例：3 份表头不一致的门店报表。"""
    ws = Path(workspace)
    raw = ws / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    base_header = ["order_id", "order_date", "region", "channel", "qty", "unit_price"]
    rng = random.Random(11)
    for idx, region in enumerate(REGIONS):
        header = list(base_header)
        if region == "华东":
            header.append("备注")
        if region == "华南":
            header.remove("channel")
        rows = []
        for i in range(1, 21):
            row = {
                "order_id": f"{region[:1]}D{idx}{i:04d}",
                "order_date": f"2026-09-{rng.randint(1, 28):02d}",
                "region": region,
                "channel": rng.choice(CHANNELS),
                "qty": rng.randint(1, 15),
                "unit_price": round(rng.uniform(30, 500), 2),
                "备注": "含运费" if i % 5 == 0 else "",
            }
            if region == "华南":
                row.pop("channel", None)
            rows.append([row.get(col, "") for col in header])
        _write_csv(raw / f"sales_{region}.csv", header, rows)
    return {"files": len(REGIONS), "raw_dir": str(raw)}


def make_split_sample(workspace: str | Path) -> dict:
    """只生成「按列拆表」的样例：一张 90 行的总表。"""
    ws = Path(workspace)
    raw = ws / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    path = _make_split_csv(raw)
    return {"split_source": str(path)}


def make_all(workspace: str | Path) -> dict:
    ws = Path(workspace)
    inbox = ws / "inbox"
    raw = ws / "raw"
    out = ws / "out"

    for d in (inbox, raw, out):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    file_count = _touch_files(inbox)
    make_merge_samples(ws)
    split_csv = _make_split_csv(raw)

    return {
        "inbox_files": file_count,
        "inbox_dir": str(inbox),
        "raw_dir": str(raw),
        "split_source": str(split_csv),
        "out_dir": str(out),
    }


if __name__ == "__main__":
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from kit.common import setup_console

    setup_console()
    info = make_all(Path(__file__).resolve().parent.parent / "workspace")
    print(json.dumps(info, ensure_ascii=False, indent=2))
