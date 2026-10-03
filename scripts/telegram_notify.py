#!/usr/bin/env python3
"""텔레그램 전송 (urllib). 다이제스트 코드를 import하지 않는다 — 저장소 사이에는 파일만 오간다."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

_MAX_CHARS = 4000  # 텔레그램 한 메시지 상한 4096자


def telegram_configured() -> bool:
    return bool(
        (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        and (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    )


def _chunks(text: str) -> list[str]:
    """줄 단위로 끊어 상한 안에 담는다. 한 줄이 상한보다 길면 그 줄을 자른다."""
    out: list[str] = []
    cur = ""
    for line in text.splitlines(keepends=True):
        while len(line) > _MAX_CHARS:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:_MAX_CHARS])
            line = line[_MAX_CHARS:]
        if len(cur) + len(line) > _MAX_CHARS:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return out


def send_telegram_text(text: str) -> bool:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for part in _chunks(text.strip()):
        body = json.dumps(
            {
                "chat_id": chat_id,
                "text": part.strip(),
                "disable_web_page_preview": True,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                if not 200 <= r.status < 300:
                    return False
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"Telegram 전송 실패: {e}", file=sys.stderr)
            return False
    return True
