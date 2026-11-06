import os

from dotenv import load_dotenv
from fastapi import FastAPI, Query
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": os.getenv("APP_ENV", "development")}


@app.get("/api/statutes/search", response_model=list[StatuteHit])
def search_statutes(
    q: str = Query(min_length=1, max_length=200, description="自然语言查询"),
    limit: int = Query(default=5, ge=1, le=20),
) -> list[StatuteHit]:
    conn = db.connect()
    try:
        rows = db.search(conn, q, limit)
    finally:
        conn.close()
    return [
        StatuteHit(
            law_name=row["law_name"],
            article_no=row["article_no"],
            article_index=row["article_index"],
            text=row["text"],
            source_url=row["source_url"],
            score=row["score"],
        )
        for row in rows
    ]
