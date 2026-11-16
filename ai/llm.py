"""
LLM client cho Hụi On-Chain.

Dùng Google Gemini (gemini-2.0-flash) — có free tier qua Google AI Studio:
  - 15 req/phút, 1500/ngày trên free tier
  - Lấy key tại https://aistudio.google.com/app/apikey
  - Export GEMINI_API_KEY=<key> trước khi chạy app

Cài đặt trực tiếp REST API (chỉ cần `requests`, đã có sẵn) — KHÔNG phụ
thuộc google-generativeai package, để chạy được trên môi trường hạn chế.

Nếu không có key hoặc mạng lỗi: `chat()` trả về fallback cố định, để agent
chạy được ở chế độ demo/preview mà không crash.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
TIMEOUT_SEC = 20
MAX_RETRIES = 2


def _get_api_key() -> Optional[str]:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _post(payload: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    url = f"{GEMINI_ENDPOINT}?key={api_key}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(
    system_prompt: str,
    user_prompt: str,
    *,
    tools: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Gọi Gemini. Trả về dict có:
      - text:       str  — lời khuyên cuối (nếu model không gọi tool)
      - tool_calls: list — các tool model muốn gọi [{name, args}]
      - raw:        dict — JSON nguyên từ API (debug)
      - ok:         bool
      - error:      str  — nếu có lỗi

    Khi không có GEMINI_API_KEY hoặc mạng lỗi, trả về fallback `ok=False`
    và `text` chứa câu gợi ý chung chung để app không crash.
    """
    api_key = _get_api_key()
    if not api_key:
        return {
            "ok": False,
            "error": "no_api_key",
            "text": (
                "Chưa cấu hình GEMINI_API_KEY. Tôi tạm thời không đọc được "
                "lịch sử ví. Hãy đặt key (xem README) để bật trợ lý AI."
            ),
            "tool_calls": [],
            "raw": {},
        }

    contents: List[Dict[str, Any]] = []
    if history:
        for h in history[-6:]:  # giữ context ngắn
            role = "model" if h.get("role") in ("assistant", "model") else "user"
            contents.append({"role": role,
                             "parts": [{"text": h["content"]}]})

    contents.append({"role": "user", "parts": [{"text": user_prompt}]})

    payload: Dict[str, Any] = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 800,
        },
    }
    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    last_err: Optional[str] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = _post(payload, api_key)
            return _parse_gemini_response(resp)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code == 429:
                last_err = "rate_limited"
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = f"network: {e.__class__.__name__}"
            break
        except Exception as e:
            last_err = f"{e.__class__.__name__}: {e}"
            break

    return {
        "ok": False,
        "error": last_err or "unknown",
        "text": (
            "Tôi không kết nối được tới model Gemini lúc này. Vui lòng thử "
            "lại sau, hoặc xem điểm uy tín ở tab Điểm uy tín."
        ),
        "tool_calls": [],
        "raw": {},
    }


def _parse_gemini_response(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Trích text và tool_calls từ response của Gemini."""
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []

    candidates = resp.get("candidates", [])
    if not candidates:
        return {"ok": False, "error": "empty_response",
                "text": "", "tool_calls": [], "raw": resp}

    content = candidates[0].get("content", {})
    for part in content.get("parts", []):
        if "text" in part:
            text_parts.append(part["text"])
        if "functionCall" in part:
            fc = part["functionCall"]
            tool_calls.append({
                "name": fc.get("name", ""),
                "args": fc.get("args", {}),
            })

    return {
        "ok": True,
        "text": "\n".join(text_parts).strip(),
        "tool_calls": tool_calls,
        "raw": resp,
    }
