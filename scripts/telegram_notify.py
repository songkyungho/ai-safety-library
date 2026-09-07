#!/usr/bin/env python3
"""텔레그램 전송 — Digest(AI Safety) utils를 재사용. 없으면 최소 urllib 폴백."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_DIGEST_UTILS = (
    Path(__file__).resolve().parent.parent.parent / "AI Safety" / "utils"
)
if _DIGEST_UTILS.is_dir() and str(_DIGEST_UTILS.parent) not in sys.path:
    sys.path.insert(0, str(_DIGEST_UTILS.parent))

try:
    from utils.telegram_notify import (  # type: ignore
        send_telegram_text,
        telegram_configured,
    )
except ImportError:

    def telegram_configured() -> bool:
        return bool(
            (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
            and (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
        )

    def send_telegram_text(text: str) -> bool:
        token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
        if not token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = json.dumps(
            {
                "chat_id": chat_id,
                "text": text.strip(),
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
                return 200 <= r.status < 300
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"Telegram 전송 실패: {e}", file=sys.stderr)
            return False
