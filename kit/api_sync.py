"""接口对接：分页拉取 + 失败重试 + 落盘，全程离线可演示。

包含一个内置的本地 Mock 服务（http://127.0.0.1:<随机端口>），
它会刻意让每一页的首次请求返回 503，用来验证重试与幂等逻辑；
投标现场没有外网也能完整跑通整条链路。
"""
from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .common import ensure_dir, write_csv, write_text

REGIONS = ["华东", "华北", "华南", "西南", "华中"]
CHANNELS = ["官网", "天猫", "京东", "线下门店", "小程序"]
CATEGORIES = ["办公耗材", "数码配件", "清洁用品", "包装材料"]
STATUSES = ["已支付", "已支付", "已支付", "待支付", "已取消"]


def _fake_orders(total: int = 137, seed: int = 20261020) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(1, total + 1):
        qty = rng.randint(1, 12)
        price = round(rng.uniform(18, 890), 2)
        rows.append(
            {
                "order_id": f"SO2026{i:05d}",
                "order_date": f"2026-{rng.randint(7, 9):02d}-{rng.randint(1, 28):02d}",
                "region": rng.choice(REGIONS),
                "channel": rng.choice(CHANNELS),
                "category": rng.choice(CATEGORIES),
                "qty": qty,
                "unit_price": price,
                "amount": round(qty * price, 2),
                "status": rng.choice(STATUSES),
            }
        )
    return rows


class _Handler(BaseHTTPRequestHandler):
    orders: list[dict] = []
    fail_first_hit: bool = True
    _hits: dict[str, int] = {}
    _lock = threading.Lock()

    def log_message(self, *args):  # 静默，避免污染演示输出
        pass

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._json({"status": "ok", "count": len(self.orders)})
        if parsed.path != "/api/orders":
            return self._json({"error": "not found"}, 404)

        query = parse_qs(parsed.query)
        page = int(query.get("page", ["1"])[0])
        size = int(query.get("size", ["20"])[0])

        if self.fail_first_hit:
            with self._lock:
                hit = self._hits.get(f"{page}", 0)
                self._hits[f"{page}"] = hit + 1
            if hit == 0:  # 模拟首次抖动
                return self._json({"error": "upstream busy"}, 503)

        start = (page - 1) * size
        total_pages = (len(self.orders) + size - 1) // size
        self._json(
            {
                "page": page,
                "size": size,
                "total_pages": total_pages,
                "total": len(self.orders),
                "items": self.orders[start : start + size],
            }
        )

    def _json(self, payload: dict, code: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MockServer:
    """上下文管理器：with MockServer() as srv: srv.base_url"""

    def __init__(self, total: int = 137, fail_first_hit: bool = True):
        _Handler.orders = _fake_orders(total)
        _Handler.fail_first_hit = fail_first_hit
        _Handler._hits = {}
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self._httpd.server_address[1]
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        for _ in range(50):  # 等待端口就绪
            try:
                urllib.request.urlopen(f"{self.base_url}/health", timeout=1).read()
                break
            except Exception:
                time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()


def _get_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sync_orders(
    base_url: str,
    out_csv: str | Path,
    log_path: str | Path | None = None,
    page_size: int = 25,
    max_retries: int = 4,
    timeout: float = 5.0,
) -> dict:
    """分页拉取全部订单并落盘。失败按指数退避重试，超过上限则中断并保留日志。"""
    rows: list[dict] = []
    events: list[str] = []
    page, total_pages = 1, 1
    retries = 0
    started = time.time()

    while page <= total_pages:
        attempt = 0
        while True:
            url = f"{base_url}/api/orders?page={page}&size={page_size}"
            try:
                payload = _get_json(url, timeout=timeout)
                total_pages = payload.get("total_pages", 1)
                rows.extend(payload.get("items", []))
                events.append(f"page {page}/{total_pages} ok, {len(payload.get('items', []))} rows")
                page += 1
                break
            except urllib.error.HTTPError as exc:
                attempt += 1
                retries += 1
                events.append(f"page {page} HTTP {exc.code} attempt {attempt}")
                if attempt > max_retries:
                    raise RuntimeError(f"第 {page} 页连续失败 {max_retries} 次，已中止") from exc
                time.sleep(min(0.2 * 2 ** (attempt - 1), 2.0))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                attempt += 1
                retries += 1
                events.append(f"page {page} error {type(exc).__name__} attempt {attempt}")
                if attempt > max_retries:
                    raise RuntimeError(f"第 {page} 页网络异常，已中止") from exc
                time.sleep(min(0.2 * 2 ** (attempt - 1), 2.0))

    header = ["order_id", "order_date", "region", "channel", "category", "qty", "unit_price", "amount", "status"]
    write_csv(out_csv, header, rows)

    stats = {
        "rows": len(rows),
        "pages": total_pages,
        "retries": retries,
        "elapsed_s": round(time.time() - started, 2),
        "output": str(out_csv),
    }
    if log_path:
        write_text(log_path, "\n".join([f"# 同步日志 {time.strftime('%Y-%m-%d %H:%M:%S')}"] + events + ["", json.dumps(stats, ensure_ascii=False)]))
    return stats


def produce_local_api_sample(out_csv: str | Path, total: int = 137) -> dict:
    """不启服务、直接产出同样的数据，用于对比「有接口」和「只有文件」两种输入。"""
    rows = _fake_orders(total)
    header = ["order_id", "order_date", "region", "channel", "category", "qty", "unit_price", "amount", "status"]
    ensure_dir(Path(out_csv).parent)
    write_csv(out_csv, header, rows)
    return {"rows": len(rows), "output": str(out_csv)}
