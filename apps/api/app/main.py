import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import db

load_dotenv()

app = FastAPI(title="LexLens API", version="0.1.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3010,http://127.0.0.1:3010"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


class StatuteHit(BaseModel):
    law_name: str
    article_no: str
    article_index: int
    text: str
    source_url: str
    score: float


class SearchResponse(BaseModel):
    items: list[StatuteHit]
    total: int
    terms: list[str]


class ContextItem(BaseModel):
    article_no: str
    article_index: int
    text: str
    is_target: bool


class JudgmentHit(BaseModel):
    case_no: str
    court: str
    trial_level: str
    judgment_date: str | None
    cause: str | None
    project_type: str | None
    dispute_types: list[str]
    cited_statutes: list[str]
    holding: str
    reasoning: str | None
    source_url: str | None


class JudgmentSearchResponse(BaseModel):
    items: list[JudgmentHit]
    total: int
    terms: list[str]


class LawSource(BaseModel):
    law_name: str
    level: str
    version: str | None
    effective_date: str | None
    source_url: str
    fetched_at: str
    article_count: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": os.getenv("APP_ENV", "development")}


@app.get("/api/statutes/search", response_model=SearchResponse)
def search_statutes(
    q: str = Query(min_length=1, max_length=200, description="自然语言查询"),
    limit: int = Query(default=10, ge=1, le=20),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    conn = db.connect()
    try:
        rows, total = db.search(conn, q, limit, offset)
    finally:
        conn.close()
    return SearchResponse(
        items=[
            StatuteHit(
                law_name=row["law_name"],
                article_no=row["article_no"],
                article_index=row["article_index"],
                text=row["text"],
                source_url=row["source_url"],
                score=row["score"],
            )
            for row in rows
        ],
        total=total,
        terms=db.query_terms(q),
    )


@app.get("/api/judgments/search", response_model=JudgmentSearchResponse)
def judgment_search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> JudgmentSearchResponse:
    """类案检索，元数据与裁判要旨一并返回。"""
    conn = db.connect()
    try:
        rows, total = db.search_judgments(conn, q, limit, offset)
    finally:
        conn.close()
    return JudgmentSearchResponse(
        items=[
            JudgmentHit(
                case_no=row["case_no"],
                court=row["court"],
                trial_level=row["trial_level"],
                judgment_date=row["judgment_date"],
                cause=row["cause"],
                project_type=row["project_type"],
                dispute_types=json.loads(row["dispute_types"]),
                cited_statutes=json.loads(row["cited_statutes"]),
                holding=row["holding"],
                reasoning=row["reasoning"],
                source_url=row["source_url"],
            )
            for row in rows
        ],
        total=total,
        terms=db.query_terms(q),
    )


@app.get("/api/statutes/context", response_model=list[ContextItem])
def statute_context(
    law_name: str = Query(min_length=1, max_length=80),
    article_index: int = Query(ge=1),
    span: int = Query(default=2, ge=0, le=5),
) -> list[ContextItem]:
    """返回目标条文及其前后文，供引用核验。"""
    conn = db.connect()
    try:
        rows = db.articles_around(conn, law_name, article_index, span)
    finally:
        conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail="未找到该条文")
    return [
        ContextItem(
            article_no=row["article_no"],
            article_index=row["article_index"],
            text=row["text"],
            is_target=row["article_index"] == article_index,
        )
        for row in rows
    ]


@app.get("/api/statutes/sources", response_model=list[LawSource])
def list_sources() -> list[LawSource]:
    """知识库版本清单：每部法源的版本、生效日、来源与抓取时间。"""
    conn = db.connect()
    try:
        rows = conn.execute(
            """
            SELECT law_name, level, version, effective_date, source_url,
                   MAX(fetched_at) AS fetched_at, COUNT(*) AS article_count
            FROM statutes
            GROUP BY law_name, level, version, effective_date, source_url
            ORDER BY law_name
            """
        ).fetchall()
    finally:
        conn.close()
    return [LawSource(**dict(row)) for row in rows]
