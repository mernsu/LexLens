"""SQLite 存储与 FTS5 检索。

中文检索的关键：FTS5 内置分词器按空白和标点切分，整段中文会变成一个词，检索失效。
所以入库与查询都先按「相邻两字」切成二元组（建设 → 建设），再交给 FTS5 做 BM25。
用二元组不用词典分词：法律术语形态多变（优先受偿 / 优先受偿权），二元组不依赖词典，
天然覆盖这种词形差异，也不会因词典缺词导致零结果。
"""

import json
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

CREATE TABLE IF NOT EXISTS judgments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_no TEXT NOT NULL UNIQUE,
    court TEXT NOT NULL,
    trial_level TEXT NOT NULL,
    judgment_date TEXT,
    cause TEXT,
    project_type TEXT,
    dispute_types TEXT NOT NULL DEFAULT '[]',
    cited_statutes TEXT NOT NULL DEFAULT '[]',
    holding TEXT NOT NULL,
    reasoning TEXT,
    full_text TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    anonymized INTEGER NOT NULL DEFAULT 1,
    content_hash TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS judgments_fts USING fts5(
    case_no,
    holding,
    reasoning,
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


def articles_around(
    conn: sqlite3.Connection, law_name: str, article_index: int, span: int
) -> list[sqlite3.Row]:
    """取某条及其前后各 span 条，供核验上下文使用。"""
    return conn.execute(
        """
        SELECT article_no, article_index, text
        FROM statutes
        WHERE law_name = ? AND article_index BETWEEN ? AND ?
        ORDER BY article_index
        """,
        (law_name, article_index - span, article_index + span),
    ).fetchall()


def judgment_tokens(record: dict) -> str:
    """案号、案由、工程类型、争议类型、要旨、本院认为，统一切成二元组。"""
    parts = [
        record.get("case_no", ""),
        record.get("cause") or "",
        record.get("project_type") or "",
        " ".join(record.get("dispute_types") or []),
        record.get("holding") or "",
        record.get("reasoning") or "",
    ]
    return tokenize(" ".join(parts))


def upsert_judgment(conn: sqlite3.Connection, record: dict) -> str:
    """按案号写入，内容未变则跳过。返回 inserted / updated / unchanged。"""
    existing = conn.execute(
        "SELECT id, content_hash FROM judgments WHERE case_no = ?",
        (record["case_no"],),
    ).fetchone()
    if existing and existing["content_hash"] == record["content_hash"]:
        return "unchanged"

    columns = (
        "case_no", "court", "trial_level", "judgment_date", "cause",
        "project_type", "dispute_types", "cited_statutes", "holding",
        "reasoning", "full_text", "source", "source_url", "anonymized",
        "content_hash", "fetched_at",
    )
    values = tuple(
        json.dumps(record[column], ensure_ascii=False)
        if column in ("dispute_types", "cited_statutes")
        else record.get(column)
        for column in columns
    )

    if existing:
        assignments = ", ".join(f"{column} = ?" for column in columns[1:])
        conn.execute(
            f"UPDATE judgments SET {assignments} WHERE id = ?", values[1:] + (existing["id"],)
        )
        conn.execute("DELETE FROM judgments_fts WHERE rowid = ?", (existing["id"],))
        row_id, status = existing["id"], "updated"
    else:
        placeholders = ", ".join("?" for _ in columns)
        cursor = conn.execute(
            f"INSERT INTO judgments ({', '.join(columns)}) VALUES ({placeholders})", values
        )
        row_id, status = cursor.lastrowid, "inserted"

    conn.execute(
        """
        INSERT INTO judgments_fts (rowid, case_no, holding, reasoning, tokens)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            row_id,
            record["case_no"],
            record["holding"],
            record.get("reasoning") or "",
            judgment_tokens(record),
        ),
    )
    conn.commit()
    return status


def search_judgments(
    conn: sqlite3.Connection, query: str, limit: int = 10, offset: int = 0
) -> tuple[list[sqlite3.Row], int]:
    """与法条检索同一策略：全词 AND 优先，退到 OR 后按覆盖率重排。"""
    words = query_tokens(query)
    if not words:
        return [], 0
    sql = """
        SELECT j.case_no, j.court, j.trial_level, j.judgment_date, j.cause,
               j.project_type, j.dispute_types, j.cited_statutes, j.holding,
               j.reasoning, j.source_url, f.tokens AS indexed_tokens,
               bm25(judgments_fts) AS score
        FROM judgments_fts f
        JOIN judgments j ON j.id = f.rowid
        WHERE judgments_fts MATCH ?
        ORDER BY score
        LIMIT ? OFFSET ?
    """
    count_sql = "SELECT COUNT(*) FROM judgments_fts WHERE judgments_fts MATCH ?"

    expression = _expression(words, " ")
    total = conn.execute(count_sql, (expression,)).fetchone()[0]
    if total:
        return conn.execute(sql, (expression, limit, offset)).fetchall(), total

    candidates = conn.execute(
        """
        SELECT j.case_no, j.court, j.trial_level, j.judgment_date, j.cause,
               j.project_type, j.dispute_types, j.cited_statutes, j.holding,
               j.reasoning, j.source_url, f.tokens AS indexed_tokens,
               bm25(judgments_fts) AS score
        FROM judgments_fts f
        JOIN judgments j ON j.id = f.rowid
        WHERE judgments_fts MATCH ?
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

