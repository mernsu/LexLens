"""法条入库命令行。

单部入库：
    uv run python -m app.ingest --law-name 中华人民共和国民法典 \
        --url https://www.court.gov.cn/zixun/xiangqing/233181.html \
        --effective-date 2021-01-01 --expected-count 1260

按清单批量入库（默认读 knowledge/sources.json）：
    uv run python -m app.ingest --manifest
"""

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any

from app import db
from app.statute_parser import html_to_text, parse_articles, validate_articles

USER_AGENT = "Mozilla/5.0 (compatible; LexLens/0.1; +legal research workspace)"
DEFAULT_MANIFEST = Path("knowledge/sources.json")


def load_source(url: str | None, file: Path | None, base_dir: Path) -> str:
    if url:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", "ignore")
    if file:
        return (base_dir / file).read_text(encoding="utf-8")
    raise SystemExit("必须提供 --url 或 --file")


def ingest_entry(conn: Any, entry: dict[str, Any], base_dir: Path) -> int:
    file = Path(entry["file"]) if entry.get("file") else None
    raw = load_source(entry.get("url"), file, base_dir)
    articles = parse_articles(html_to_text(raw))
    validate_articles(articles, expected_count=entry.get("expected_count"))

    inserted = db.replace_articles(
        conn,
        law_name=entry["law_name"],
        level=entry.get("level", "法律"),
        source_url=entry.get("url") or entry["file"],
        effective_date=entry.get("effective_date"),
        version=entry.get("version"),
        articles=[(item.article_no, item.index, item.text) for item in articles],
    )
    print(
        f"入库 {entry['law_name']}：{inserted} 条"
        f"（{articles[0].article_no} 至 {articles[-1].article_no}）"
    )
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="法条入库")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="法条全文页面地址")
    source.add_argument("--file", type=Path, help="本地 HTML/文本文件")
    source.add_argument(
        "--manifest",
        nargs="?",
        const=str(DEFAULT_MANIFEST),
        default=None,
        help=f"按清单批量入库，默认 {DEFAULT_MANIFEST}",
    )
    parser.add_argument("--law-name", default=None)
    parser.add_argument("--level", default="法律")
    parser.add_argument("--effective-date", default=None)
    parser.add_argument("--version", default=None, help="版本或文号说明")
    parser.add_argument("--expected-count", type=int, default=None)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    conn = db.connect(args.db_path)
    target = db.db_path() if args.db_path is None else args.db_path

    if args.manifest:
        manifest_path = Path(args.manifest)
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in entries:
            ingest_entry(conn, entry, manifest_path.parent)
        total = sum(
            conn.execute(
                "SELECT COUNT(*) FROM statutes WHERE law_name = ?", (entry["law_name"],)
            ).fetchone()[0]
            for entry in entries
        )
        print(f"清单 {len(entries)} 部，共 {total} 条，数据库 {target}")
        return

    if not args.law_name:
        parser.error("单部入库需提供 --law-name")

    inserted = ingest_entry(
        conn,
        {
            "law_name": args.law_name,
            "level": args.level,
            "url": args.url,
            "file": str(args.file) if args.file else None,
            "effective_date": args.effective_date,
            "version": args.version,
            "expected_count": args.expected_count,
        },
        Path("."),
    )
    print(f"入库 {inserted} 条，数据库 {target}")


if __name__ == "__main__":
    main()
