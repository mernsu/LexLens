"""法条入库命令行。

用法：
    uv run python -m app.ingest --law-name 中华人民共和国民法典 \
        --url https://www.court.gov.cn/zixun/xiangqing/233181.html \
        --effective-date 2021-01-01 --expected-count 1260
"""

import argparse
import urllib.request
from pathlib import Path

from app import db
from app.statute_parser import html_to_text, parse_articles, validate_articles

USER_AGENT = "Mozilla/5.0 (compatible; LexLens/0.1; +legal research workspace)"


def load_source(url: str | None, file: Path | None) -> str:
    if url:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", "ignore")
    if file:
        return file.read_text(encoding="utf-8")
    raise SystemExit("必须提供 --url 或 --file")


def main() -> None:
    parser = argparse.ArgumentParser(description="法条入库")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="法条全文页面地址")
    source.add_argument("--file", type=Path, help="本地 HTML/文本文件")
    parser.add_argument("--law-name", required=True)
    parser.add_argument("--level", default="法律")
    parser.add_argument("--effective-date", default=None)
    parser.add_argument("--version", default=None, help="修正版本说明")
    parser.add_argument("--expected-count", type=int, default=None)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    raw = load_source(args.url, args.file)
    articles = parse_articles(html_to_text(raw))
    validate_articles(articles, expected_count=args.expected_count)

    conn = db.connect(args.db_path)
    inserted = db.replace_articles(
        conn,
        law_name=args.law_name,
        level=args.level,
        source_url=args.url or str(args.file),
        effective_date=args.effective_date,
        version=args.version,
        articles=[(item.article_no, item.index, item.text) for item in articles],
    )
    print(f"入库 {args.law_name}：{inserted} 条")
    print(f"首条 {articles[0].article_no}，末条 {articles[-1].article_no}")
    print(f"数据库 {db.db_path() if args.db_path is None else args.db_path}")


if __name__ == "__main__":
    main()
