#!/usr/bin/env python3
"""AI Safety Library MCP 서버.

knowledge/library.db (FTS5 trigram + 임베딩)를 읽어 법·가이드라인·정책 문서 검색 도구를 제공한다.
반드시 python 3.10+ 전용 venv($HOME/.venvs/ai-safety-library-mcp)에서 실행할 것
— mcp_server/README.md 참고.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

ENV_CANDIDATES = (
    Path.home() / ".ai_safety_daily_env",
    REPO_ROOT.parent / "AI Safety" / "ai_safety_daily_env",
    REPO_ROOT / "ai_safety_library_env",
)


def _bootstrap_env() -> None:
    for path in ENV_CANDIDATES:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val


_bootstrap_env()

from mcp.server.fastmcp import FastMCP  # noqa: E402

DB_PATH = REPO_ROOT / "knowledge" / "library.db"
RRF_K = 60

mcp = FastMCP("ai-safety-library")

_embed_cache: dict[str, Any] = {}

RESULT_COLS = [
    "id",
    "url",
    "short_name",
    "title",
    "original_name",
    "summary",
    "doc_kind",
    "country",
    "country_ko",
    "org",
    "published",
    "issuer_level",
    "issuer_level_ko",
    "status_ko",
    "topics",
    "in_scope",
]


def _connect() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise RuntimeError(
            f"{DB_PATH} 없음 — 먼저 `python3 mcp_server/build_index.py` 실행 필요"
        )
    return sqlite3.connect(str(DB_PATH))


def _fts_query(topic: str) -> str:
    escaped = topic.replace('"', '""').strip()
    return f'"{escaped}"'


def _row_to_dict(row: tuple, cols: list[str]) -> dict[str, Any]:
    d = dict(zip(cols, row))
    topics = d.get("topics") or ""
    d["topics"] = [t.strip() for t in topics.split(",") if t.strip()]
    d["in_scope"] = bool(d.get("in_scope"))
    d.pop("embedding", None)
    d.pop("content_hash", None)
    return d


def _load_embeddings(conn: sqlite3.Connection):
    import numpy as np

    if "matrix" in _embed_cache:
        return _embed_cache["ids"], _embed_cache["matrix"]
    cur = conn.execute("SELECT id, embedding FROM items WHERE embedding IS NOT NULL")
    ids: list[str] = []
    vecs: list[Any] = []
    for rid, blob in cur.fetchall():
        ids.append(rid)
        vecs.append(np.frombuffer(blob, dtype=np.float32))
    matrix = np.vstack(vecs) if vecs else np.zeros((0, 1536), dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1.0
    _embed_cache["ids"] = ids
    _embed_cache["matrix"] = matrix
    _embed_cache["norms"] = norms
    return ids, matrix


def _embedding_client_kwargs() -> dict[str, str]:
    if (os.environ.get("OPENROUTER_API_KEY") or "").strip():
        return {
            "api_key": os.environ["OPENROUTER_API_KEY"].strip(),
            "base_url": "https://openrouter.ai/api/v1",
        }
    return {
        "api_key": (os.environ.get("OPENAI_API_KEY") or "").strip(),
        "base_url": "https://api.openai.com/v1",
    }


def _embedding_model_id() -> str:
    if (os.environ.get("OPENROUTER_API_KEY") or "").strip():
        return "openai/text-embedding-3-small"
    return "text-embedding-3-small"


def _embed_query(topic: str):
    import numpy as np
    from openai import OpenAI

    client = OpenAI(**_embedding_client_kwargs())
    resp = client.embeddings.create(model=_embedding_model_id(), input=[topic])
    return np.array(resp.data[0].embedding, dtype=np.float32)


def _semantic_rank(conn: sqlite3.Connection, topic: str, top_n: int) -> list[str]:
    has_key = bool(
        (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        or (os.environ.get("OPENAI_API_KEY") or "").strip()
    )
    if not has_key:
        return []
    try:
        import numpy as np

        ids, matrix = _load_embeddings(conn)
        if not ids:
            return []
        q = _embed_query(topic)
        q_norm = np.linalg.norm(q) or 1.0
        sims = (matrix @ q) / (_embed_cache["norms"] * q_norm)
        order = np.argsort(-sims)[:top_n]
        return [ids[i] for i in order]
    except Exception as e:  # noqa: BLE001
        print(f"의미 검색 건너뜀: {e}", file=sys.stderr)
        return []


def _keyword_rank(conn: sqlite3.Connection, topic: str, top_n: int) -> list[str]:
    try:
        cur = conn.execute(
            """
            SELECT i.id
            FROM items_fts
            JOIN items i ON i.rowid = items_fts.rowid
            WHERE items_fts MATCH ?
            ORDER BY bm25(items_fts)
            LIMIT ?
            """,
            (_fts_query(topic), top_n),
        )
        return [r[0] for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


@mcp.tool()
def search_library(
    topic: str,
    limit: int = 15,
    in_scope_only: bool = True,
    country: str = "",
    doc_kind: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[dict[str, Any]]:
    """AI 안전 법·가이드라인·정책 라이브러리에서 주제와 관련된 문서를 검색한다.

    키워드(FTS) 검색과 의미 기반(임베딩) 검색을 함께 사용한다. 반환된 summary를
    근거로 실제 관련성을 직접 판단할 것 — 후보를 폭넓게 모아줄 뿐 최종 판단은
    호출자의 몫이다.

    Args:
        topic: 검색할 주제/키워드 (한글/영문 모두 가능).
        limit: 반환할 최대 건수 (기본 15).
        in_scope_only: True면 라이브러리 게시 범위(in_scope) 문서만 (기본 True).
        country: 국가 영문명 필터 (예: Korea, United States). 선택.
        doc_kind: 문서종류 필터 (예: 법률, 가이드라인·원칙). 선택.
        date_from: published 하한 (YYYY-MM-DD 또는 YYYY). 선택.
        date_to: published 상한. 선택.
    """
    conn = _connect()
    try:
        pool_n = max(limit * 3, 40)
        kw_ids = _keyword_rank(conn, topic, pool_n)
        sem_ids = _semantic_rank(conn, topic, pool_n)

        scores: dict[str, float] = {}
        for rank, rid in enumerate(kw_ids):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (RRF_K + rank)
        for rank, rid in enumerate(sem_ids):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (RRF_K + rank)

        if not scores:
            return []

        ordered_ids = sorted(scores, key=lambda r: -scores[r])
        placeholders = ",".join("?" for _ in ordered_ids)
        where = [f"id IN ({placeholders})"]
        params: list[Any] = list(ordered_ids)
        if in_scope_only:
            where.append("in_scope = 1")
        if country:
            where.append("(country = ? OR country_ko = ?)")
            params.extend([country, country])
        if doc_kind:
            where.append("doc_kind = ?")
            params.append(doc_kind)
        if date_from:
            where.append("published >= ?")
            params.append(date_from)
        if date_to:
            where.append("published <= ?")
            params.append(date_to)

        query = (
            f"SELECT {', '.join(RESULT_COLS)} FROM items "
            f"WHERE {' AND '.join(where)}"
        )
        rows = conn.execute(query, params).fetchall()
        by_id = {row[0]: _row_to_dict(row, RESULT_COLS) for row in rows}
        results = [by_id[rid] for rid in ordered_ids if rid in by_id]
        return results[:limit]
    finally:
        conn.close()


@mcp.tool()
def get_document(doc_id: str) -> dict[str, Any]:
    """문서 id(doc-…)로 라이브러리 항목 1건의 상세를 반환한다.

    search_library 결과의 id로 원문 URL·요약·종류·주체 등을 확인할 때 사용.
    """
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {', '.join(RESULT_COLS)} FROM items WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if not row:
            return {"error": f"문서 없음: {doc_id}"}
        return _row_to_dict(row, RESULT_COLS)
    finally:
        conn.close()


@mcp.tool()
def corpus_stats() -> dict[str, Any]:
    """라이브러리 코퍼스 규모/기간/임베딩 커버리지 요약."""
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        in_scope = conn.execute(
            "SELECT COUNT(*) FROM items WHERE in_scope = 1"
        ).fetchone()[0]
        dmin, dmax = conn.execute(
            "SELECT MIN(published), MAX(published) FROM items "
            "WHERE published != '' AND published GLOB '[0-9]*'"
        ).fetchone()
        embedded = conn.execute(
            "SELECT COUNT(*) FROM items WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        kinds = {
            k: n
            for k, n in conn.execute(
                "SELECT doc_kind, COUNT(*) FROM items "
                "WHERE in_scope = 1 AND doc_kind != '' "
                "GROUP BY doc_kind ORDER BY COUNT(*) DESC"
            ).fetchall()
        }
        return {
            "total_items": total,
            "in_scope_items": in_scope,
            "out_of_scope_items": total - in_scope,
            "published_range": [dmin, dmax],
            "embedded_items": embedded,
            "doc_kinds_in_scope": kinds,
            "semantic_search_enabled": bool(
                (os.environ.get("OPENROUTER_API_KEY") or "").strip()
                or (os.environ.get("OPENAI_API_KEY") or "").strip()
            ),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run()
