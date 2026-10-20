"""公共工具：控制台编码、日志、CSV 读写、路径处理。

设计原则：只依赖 Python 标准库，客户现场无需 pip / 无需联网即可运行。
"""
from __future__ import annotations

import csv
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------- 控制台编码
def setup_console() -> None:
    """在 Windows 中文环境下强制 UTF-8 输出，避免 GBK 编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


# ---------------------------------------------------------------- 日志
def get_logger(name: str = "kit", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


# ---------------------------------------------------------------- 路径
def ensure_dir(path: str | os.PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024
    return f"{size:.1f}TB"


# ---------------------------------------------------------------- CSV
def read_csv(path: str | os.PathLike) -> tuple[list[str], list[dict[str, str]]]:
    """读取 CSV，兼容 UTF-8 BOM 与 GBK 两种来源编码。"""
    path = Path(path)
    for enc in ("utf-8-sig", "gbk"):
        try:
            with path.open("r", encoding=enc, newline="") as fh:
                reader = csv.DictReader(fh)
                header = list(reader.fieldnames or [])
                rows = [dict(r) for r in reader]
            return header, rows
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, f"无法识别 {path} 的编码")


def write_csv(
    path: str | os.PathLike,
    header: list[str],
    rows: list[dict],
    encoding: str = "utf-8-sig",
) -> Path:
    """写出 CSV。默认带 BOM，Excel 双击打开不乱码。"""
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in header})
    return path


def write_text(path: str | os.PathLike, text: str) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    return path
