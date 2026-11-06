"""裁判文书入库命令行。

交换格式为 JSONL：一行一条记录。必填字段见 REQUIRED_FIELDS。
入库前逐条校验：必填、审级取值、日期格式、脱敏扫描；命中身份证号、
手机号或邮箱的记录整条拒收，不写入数据库。

用法：uv run python -m app.judgments --file cases.jsonl
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db

REQUIRED_FIELDS = ("case_no", "court", "trial_level", "holding", "source")
TRIAL_LEVELS = {"一审", "二审", "再审", "其他"}

_PII_PATTERNS = (
    (re.compile(r"\d{17}[\dXx]"), "身份证号"),
    (re.compile(r"1[3-9]\d{9}"), "手机号"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "邮箱"),
)


def _normalize(record: dict) -> dict:
    normalized = dict(record)
    for key in ("dispute_types", "cited_statutes"):
        value = normalized.get(key) or []
        if not isinstance(value, list):
            raise ValueError(f"{key} 必须是数组")
        normalized[key] = [str(item) for item in value]
    normalized["anonymized"] = bool(normalized.get("anonymized", True))
    normalized["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    normalized["content_hash"] = hashlib.sha256(
        "|".join(
            str(normalized.get(key) or "")
            for key in ("case_no", "holding", "reasoning", "full_text")
        ).encode("utf-8")
    ).hexdigest()
    return normalized


def validate(record: dict) -> str | None:
    """返回拒收理由；通过则返回 None。"""
    missing = [field for field in REQUIRED_FIELDS if not str(record.get(field) or "").strip()]
    if missing:
        return f"缺少必填字段：{', '.join(missing)}"
    if record["trial_level"] not in TRIAL_LEVELS:
        return f"审级取值非法：{record['trial_level']}"
    date = record.get("judgment_date")
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return f"裁判日期格式应为 YYYY-MM-DD：{date}"
    for field, label in _PII_PATTERNS:
        if field.search(json.dumps(record, ensure_ascii=False)):
            return f"疑似未脱敏（{label}）"
    return None


def ingest_file(path: Path, conn) -> dict[str, int]:
    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            print(f"第 {number} 行 JSON 解析失败：{error}", file=sys.stderr)
            stats["rejected"] += 1
            continue
        reason = validate(record)
        if reason:
            print(f"第 {number} 行拒收：{reason}", file=sys.stderr)
            stats["rejected"] += 1
            continue
        try:
            stats[db.upsert_judgment(conn, _normalize(record))] += 1
        except ValueError as error:
            print(f"第 {number} 行拒收：{error}", file=sys.stderr)
            stats["rejected"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="裁判文书 JSONL 入库")
    parser.add_argument("--file", required=True, type=Path, help="JSONL 文件")
    parser.add_argument("--db-path", type=Path, help="覆盖数据库路径")
    args = parser.parse_args()

    conn = db.connect(args.db_path)
    try:
        stats = ingest_file(args.file, conn)
    finally:
        conn.close()

    total = conn_total(args.db_path)
    print(
        f"新增 {stats['inserted']} · 更新 {stats['updated']} · "
        f"未变 {stats['unchanged']} · 拒收 {stats['rejected']} · 库内合计 {total}"
    )
    return 0


def conn_total(path: Path | None) -> int:
    conn = db.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM judgments").fetchone()[0]
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
