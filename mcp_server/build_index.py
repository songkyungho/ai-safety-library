#!/usr/bin/env python3
"""documents.json → knowledge/library.db (FTS5 + 임베딩).

- 시스템 python3(3.9+)에서 동작 (일일 파이프라인이 호출).
- FTS5 trigram 토크나이저로 한글 부분 문자열 검색 지원.
- OPENROUTER_API_KEY(우선) 또는 OPENAI_API_KEY 가 있으면 OpenRouter를 통해
  openai/text-embedding-3-small 로 의미 검색용 임베딩도 저장.
  기존 DB에 동일 본문(content_hash)의 임베딩이 있으면 재사용해 API 호출을 최소화한다.

사용법:
  python3 mcp_server/build_index.py
  python3 mcp_server/build_index.py --no-embeddings
  python3 mcp_server/build_index.py --reuse-embeddings-only
  python3 mcp_server/build_index.py --skip-if-fresh
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_PATH = REPO_ROOT / "documents.json"
DB_PATH = REPO_ROOT / "knowledge" / "library.db"
EMBED_MODEL = "openai/text-embedding-3-small"
EMBED_BATCH = 100
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

ENV_CANDIDATES = (
    Path.home() / ".ai_safety_daily_env",
    REPO_ROOT.parent / "AI Safety" / "ai_safety_daily_env",
    REPO_ROOT / "ai_safety_library_env",
)


def bootstrap_env() -> None:
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


def embedding_api_key() -> str:
    return (
        (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        or (os.environ.get("OPENAI_API_KEY") or "").strip()
    )


def embedding_client_kwargs() -> dict[str, str]:
    if (os.environ.get("OPENROUTER_API_KEY") or "").strip():
        return {
            "api_key": os.environ["OPENROUTER_API_KEY"].strip(),
            "base_url": OPENROUTER_BASE_URL,
        }
    return {
        "api_key": (os.environ.get("OPENAI_API_KEY") or "").strip(),
        "base_url": "https://api.openai.com/v1",
    }


def embedding_model_id() -> str:
    if (os.environ.get("OPENROUTER_API_KEY") or "").strip():
        return EMBED_MODEL
    return EMBED_MODEL.split("/", 1)[-1]


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def topics_text(doc: dict[str, Any]) -> str:
    parts: list[str] = []
    for t in doc.get("topics") or []:
        if isinstance(t, dict):
            parts.append(str(t.get("label") or t.get("id") or ""))
        else:
            parts.append(str(t))
    return ", ".join(p for p in parts if p)


def embed_text_for(doc: dict[str, Any]) -> str:
    title = doc.get("short_name") or doc.get("title") or ""
    summary = doc.get("summary") or doc.get("snippet") or ""
    return f"{title}\n{summary}".strip()


def load_documents(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    blob = json.loads(path.read_text(encoding="utf-8"))
    docs = blob.get("documents") or []
    return [d for d in docs if d.get("id")]


def load_existing_embeddings(db_path: Path) -> dict[str, tuple[str, bytes]]:
    out: dict[str, tuple[str, bytes]] = {}
    if not db_path.is_file():
        return out
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute(
            "SELECT id, content_hash, embedding FROM items WHERE embedding IS NOT NULL"
        )
        for row_id, c_hash, blob in cur.fetchall():
            out[row_id] = (c_hash, blob)
        conn.close()
    except sqlite3.Error:
        pass
    return out


def embed_texts(texts: list[str]) -> list[bytes]:
    import numpy as np
    from openai import OpenAI

    client = OpenAI(**embedding_client_kwargs())
    model = embedding_model_id()
    out: list[bytes] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = client.embeddings.create(model=model, input=batch)
        for item in resp.data:
            vec = np.array(item.embedding, dtype=np.float32)
            out.append(vec.tobytes())
        print(f"  임베딩 {min(i + EMBED_BATCH, len(texts))}/{len(texts)}", file=sys.stderr)
    return out


def build_db(
    docs: list[dict[str, Any]],
    *,
    use_embeddings: bool,
    generate_missing_embeddings: bool = True,
) -> None:
    existing = load_existing_embeddings(DB_PATH) if use_embeddings else {}

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE items (
            id TEXT PRIMARY KEY,
            url TEXT,
            short_name TEXT,
            title TEXT,
            original_name TEXT,
            summary TEXT,
            content_hash TEXT,
            doc_kind TEXT,
            country TEXT,
            country_ko TEXT,
            org TEXT,
            published TEXT,
            issuer_level TEXT,
            issuer_level_ko TEXT,
            status_ko TEXT,
            topics TEXT,
            in_scope INTEGER,
            embedding BLOB
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE items_fts USING fts5(
            short_name, title, original_name, summary, doc_kind,
            country, country_ko, org, topics, status_ko,
            content='items', content_rowid='rowid',
            tokenize='trigram'
        )
        """
    )

    to_embed_idx: list[int] = []
    rows: list[tuple] = []
    for idx, d in enumerate(docs):
        rid = d.get("id") or ""
        text = embed_text_for(d)
        c_hash = content_hash(text)
        blob = None
        if use_embeddings:
            cached = existing.get(rid)
            if cached and cached[0] == c_hash:
                blob = cached[1]
            else:
                to_embed_idx.append(idx)
        rows.append(
            (
                rid,
                d.get("canonical_url") or d.get("url") or "",
                d.get("short_name") or "",
                d.get("title") or "",
                d.get("original_name") or "",
                d.get("summary") or d.get("snippet") or "",
                c_hash,
                d.get("doc_kind") or "",
                d.get("country") or "",
                d.get("country_ko") or "",
                d.get("org") or "",
                d.get("published") or "",
                d.get("issuer_level") or "",
                d.get("issuer_level_ko") or "",
                d.get("status_ko") or "",
                topics_text(d),
                1 if d.get("in_scope", True) else 0,
                blob,
            )
        )

    if use_embeddings and to_embed_idx and generate_missing_embeddings:
        print(f"신규/변경 {len(to_embed_idx)}건 임베딩 생성 중...", file=sys.stderr)
        texts = [embed_text_for(docs[i]) or docs[i].get("id", "") for i in to_embed_idx]
        try:
            blobs = embed_texts(texts)
            for i, blob in zip(to_embed_idx, blobs):
                rows[i] = rows[i][:-1] + (blob,)
        except Exception as e:  # noqa: BLE001
            print(f"임베딩 생성 실패 (키워드 검색만 사용됨): {e}", file=sys.stderr)
    elif use_embeddings and to_embed_idx:
        print(
            f"기존 임베딩 없는 {len(to_embed_idx)}건은 의미 검색에서 제외 "
            "(--reuse-embeddings-only: 외부 API 호출 없음)",
            file=sys.stderr,
        )

    conn.executemany(
        """
        INSERT INTO items (
            id, url, short_name, title, original_name, summary, content_hash,
            doc_kind, country, country_ko, org, published, issuer_level,
            issuer_level_ko, status_ko, topics, in_scope, embedding
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.execute("INSERT INTO items_fts(items_fts) VALUES('rebuild')")
    conn.commit()
    n_embedded = sum(1 for r in rows if r[-1] is not None)
    n_scope = sum(1 for r in rows if r[-2] == 1)
    conn.close()
    print(
        f"library.db 생성: {len(rows)}건 (in_scope {n_scope}, 임베딩 {n_embedded}) "
        f"→ {DB_PATH.relative_to(REPO_ROOT)}"
    )


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="documents.json → library.db")
    embedding_group = parser.add_mutually_exclusive_group()
    embedding_group.add_argument(
        "--no-embeddings", action="store_true", help="임베딩 없이 키워드 검색용 DB만 생성"
    )
    embedding_group.add_argument(
        "--reuse-embeddings-only",
        action="store_true",
        help="기존 DB의 동일 본문 임베딩만 재사용하고 외부 API는 호출하지 않음",
    )
    parser.add_argument(
        "--skip-if-fresh",
        action="store_true",
        help="library.db가 documents.json보다 새로우면 재생성하지 않는다",
    )
    args = parser.parse_args(argv)

    if args.skip_if_fresh and DB_PATH.is_file() and DOCS_PATH.is_file():
        if DB_PATH.stat().st_mtime >= DOCS_PATH.stat().st_mtime:
            print("MCP 인덱스: library.db가 documents.json보다 최신 — 생략")
            return 0

    docs = load_documents(DOCS_PATH)
    if not docs:
        print(f"문서 없음: {DOCS_PATH}. 먼저 scripts/build_site.py 를 실행하세요.", file=sys.stderr)
        return 1

    use_embeddings = args.reuse_embeddings_only or (
        not args.no_embeddings and bool(embedding_api_key())
    )
    if not use_embeddings and not args.no_embeddings:
        print("OPENROUTER_API_KEY/OPENAI_API_KEY 없음 — 키워드(FTS) 검색만 지원", file=sys.stderr)

    build_db(
        docs,
        use_embeddings=use_embeddings,
        generate_missing_embeddings=not args.reuse_embeddings_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
