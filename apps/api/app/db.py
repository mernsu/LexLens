"""SQLite 存储与 FTS5 检索。

中文检索的关键：FTS5 内置分词器按空白和标点切分，整段中文会变成一个词，检索失效。
所以入库与查询都先按「相邻两字」切成二元组（建设 → 建设），再交给 FTS5 做 BM25。
用二元组不用词典分词：法律术语形态多变（优先受偿 / 优先受偿权），二元组不依赖词典，
天然覆盖这种词形差异，也不会因词典缺词导致零结果。
"""

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "lexlens.db"

_CJK = re.compile(r"[\u4e00-\u9fff]")
_TOKEN_RUN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")



SCHEMA = """
CREATE TABLE IF NOT EXISTS statutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    law_name TEXT NOT NULL,
    article_no TEXT NOT NULL,
    article_index INTEGER NOT NULL,
    level TEXT NOT NULL,
    text TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    effective_date TEXT,
    version TEXT,
    UNIQUE (law_name, article_no)
);

CREATE VIRTUAL TABLE IF NOT EXISTS statutes_fts USING fts5(
    law_name,
    article_no,
    tokens,
    tokenize = 'unicode61'
);
"""


def db_path() -> Path:
    return Path(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH)))


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _clean_words(words) -> list[str]:
    return [word.strip().replace('"', "") for word in words if word.strip()]


def tokenize(text: str) -> str:
    """中文按相邻两字切分，英文与数字按整词，去重后空格拼接。"""
    tokens: list[str] = []
    for match in _TOKEN_RUN.finditer(text):
        chunk = match.group()
        if _CJK.match(chunk[0]):
            tokens.extend(chunk[i : i + 2] for i in range(max(len(chunk) - 1, 0)))
            if len(chunk) == 1:
                tokens.append(chunk)
        else:
            tokens.append(chunk)
    return " ".join(dict.fromkeys(_clean_words(tokens)))


def query_tokens(text: str) -> list[str]:
    """查询与索引用同一套切分，保证查询词一定能命中索引词。"""
    return tokenize(text).split()


def _expression(words: list[str], operator: str) -> str:
    return f" {operator} ".join(f'"{word}"' for word in words)


def _coverage(indexed_tokens: str, words: list[str]) -> int:
    indexed = set(indexed_tokens.split())
    return sum(1 for word in words if word in indexed)



def replace_articles(
    conn: sqlite3.Connection,
    *,
    law_name: str,
    level: str,
    source_url: str,
    effective_date: str | None,
    version: str | None,
    articles: list[tuple[str, int, str]],
) -> int:
    """整部法律重新入库：先删旧数据与索引，再批量写入。"""
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    old_ids = [row[0] for row in conn.execute("SELECT id FROM statutes WHERE law_name = ?", (law_name,))]
    for statute_id in old_ids:
        conn.execute("DELETE FROM statutes_fts WHERE rowid = ?", (statute_id,))
    conn.execute("DELETE FROM statutes WHERE law_name = ?", (law_name,))

    inserted = 0
    for article_no, article_index, text in articles:
        cursor = conn.execute(
            """
            INSERT INTO statutes
                (law_name, article_no, article_index, level, text, source_url, fetched_at, effective_date, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (law_name, article_no, article_index, level, text, source_url, fetched_at, effective_date, version),
        )
        conn.execute(
            "INSERT INTO statutes_fts (rowid, law_name, article_no, tokens) VALUES (?, ?, ?, ?)",
            (cursor.lastrowid, tokenize(law_name), tokenize(article_no), tokenize(text)),
        )
        inserted += 1
    conn.commit()
    return inserted


def search(
    conn: sqlite3.Connection, query: str, limit: int = 5, offset: int = 0
) -> tuple[list[sqlite3.Row], int]:
    """先按全词 AND 求精确；无结果再退到 OR，并按命中词数重排。

    返回 (当前页结果, 总命中数)。
    """
    words = query_tokens(query)
    if not words:
        return [], 0
    sql = """
        SELECT s.law_name, s.article_no, s.article_index, s.text, s.source_url,
               f.tokens AS indexed_tokens, bm25(statutes_fts) AS score
        FROM statutes_fts f
        JOIN statutes s ON s.id = f.rowid
        WHERE statutes_fts MATCH ?
        ORDER BY score
        LIMIT ? OFFSET ?
    """
    count_sql = "SELECT COUNT(*) FROM statutes_fts WHERE statutes_fts MATCH ?"

    expression = _expression(words, " ")
    total = conn.execute(count_sql, (expression,)).fetchone()[0]
    if total:
        return conn.execute(sql, (expression, limit, offset)).fetchall(), total

    # OR 兜底需要先取候选再按覆盖率排序，分页在内存里切
    candidates = conn.execute(
        """
        SELECT s.law_name, s.article_no, s.article_index, s.text, s.source_url,
               f.tokens AS indexed_tokens, bm25(statutes_fts) AS score
        FROM statutes_fts f
        JOIN statutes s ON s.id = f.rowid
        WHERE statutes_fts MATCH ?
        ORDER BY score
        LIMIT 500
        """,
        (_expression(words, " OR "),),
    ).fetchall()
    ranked = sorted(
        candidates,
        key=lambda row: (-_coverage(row["indexed_tokens"], words), row["score"]),
    )
    return ranked[offset : offset + limit], len(ranked)


def query_terms(query: str) -> list[str]:
    """查询串里的原始词，供前端高亮使用。"""
    return [word for word in _TOKEN_RUN.findall(query) if len(word) >= 2]

