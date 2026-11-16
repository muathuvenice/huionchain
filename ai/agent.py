"""
AI agent cho Hụi On-Chain.

VAI TRÒ
-------
Agent KHÔNG tính toán. Nó chọn gọi tool nào và viết lời khuyên.
Mọi con số trong câu trả lời phải đến từ `ai/tools.py` — nếu không,
guardrail `_numbers_are_grounded()` sẽ chặn và trả về câu trả lời an toàn.

Đây là lý do có thể kiểm toán: cùng một dữ liệu on-chain, cùng một bộ tool,
ai chạy lại cũng ra cùng con số. Chỉ phần diễn đạt là khác nhau.

VÒNG LẶP
--------
1. Model thấy câu hỏi + danh sách tool + dữ liệu dây hụi
2. Model chọn gọi 1..N tool (functionCall)
3. Ta chạy tool, đưa kết quả lại cho model
4. Model viết lời khuyên cuối cùng
5. Guardrail kiểm tra mọi số trong câu trả lời có khớp tool output không
6. Nếu có số lạ → trả về lời khuyên fallback deterministic

Tối đa 3 vòng để tránh vòng lặp vô hạn và giữ thời gian phản hồi <30s.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ai import llm, tools
from ai.credit_score import History

MAX_STEPS = 3

SYSTEM_PROMPT = """Bạn là trợ lý tài chính cho "Hụi On-Chain" — một dây hụi (ROSCA) \
chạy trên hợp đồng thông minh ở Avalanche, dùng USDC.

NGUYÊN TẮC BẮT BUỘC:

1. MỌI CON SỐ bạn nêu ra phải lấy từ kết quả tool. Không bao giờ tự tính, \
tự ước lượng, hay tự bịa. Nếu chưa có số, gọi tool trước.

2. Trần lãi 20%/năm là giới hạn pháp lý Việt Nam (Điều 468 BLDS 2015), \
được cưỡng chế trong contract. Không bao giờ gợi ý vượt trần.

3. Hụi là zero-sum: người nhận sớm LỖ, người nhận muộn LỜI. Không có lãi \
từ bên ngoài. Nếu người dùng tưởng có lãi cao, phải nói thẳng là hiểu nhầm.

4. Bạn KHÔNG phải cố vấn đầu tư. Đưa ra thông tin và hệ quả để người dùng \
tự quyết. Không hứa hẹn lợi nhuận, không khuyên vay tiền để chơi hụi.

5. Nếu tool trả về lỗi hoặc thiếu dữ liệu, nói thật là không có dữ liệu. \
Không đoán.

6. Trả lời bằng tiếng Việt, ngắn gọn, thân thiện. Dùng số có dấu phân cách \
(1.000.000). Nêu rõ đâu là dữ kiện, đâu là giả định.

7. Khi nói về rủi ro bùng hụi: người đã nhận pot không còn gì để mất ngoài \
ký quỹ 1 kỳ. Đây là rủi ro thật, đừng tô hồng."""


# ── Khai báo tool cho Gemini function calling ────────────────────
TOOL_DECLS: List[Dict[str, Any]] = [
    {
        "name": "explain_credit_score",
        "description": (
            "Giải thích điểm uy tín của một ví: điểm, hạng, phân rã 5 thành "
            "phần có trọng số, và gợi ý cải thiện. Dùng khi người dùng hỏi "
            "về điểm tín dụng, hoặc hỏi vì sao điểm thấp/cao."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "address": {"type": "string",
                            "description": "Địa chỉ ví cần chấm điểm"},
            },
            "required": ["address"],
        },
    },
    {
        "name": "circle_status",
        "description": (
            "Xem trạng thái dây hụi hiện tại: đang ở kỳ mấy, ai đã nhận pot, "
            "còn bao nhiêu người chưa nhận, quỹ phạt. Dùng khi người dùng hỏi "
            "về chiến lược chơi, hoặc tình hình dây."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "simulate_bid",
        "description": (
            "Mô phỏng: nếu kêu giá X và nhận pot ở vòng Y thì lãi/lỗ ròng bao "
            "nhiêu. Dùng khi người dùng hỏi nên kêu giá bao nhiêu, hoặc hỏi "
            "nhận sớm/muộn thì được gì mất gì."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "bid": {"type": "integer",
                        "description": "Giá kêu mỗi kỳ (đơn vị token)"},
                "receive_round": {
                    "type": "integer",
                    "description": "Vòng dự kiến nhận pot (1-based)",
                },
            },
            "required": ["bid", "receive_round"],
        },
    },
    {
        "name": "bid_advice",
        "description": (
            "Gợi ý 3 mức giá kêu (an toàn / vừa phải / cần tiền gấp) kèm hệ "
            "quả lãi lỗ từng mức. Dùng khi người dùng chưa biết nên kêu bao "
            "nhiêu, cần tham khảo dải giá."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "defi_pools",
        "description": (
            "Lấy danh sách pool lending có APY tốt trên Avalanche. Dùng khi "
            "người dùng hỏi về yield, gửi tiền nhàn rỗi đi đâu."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "top": {"type": "integer",
                        "description": "Số pool muốn lấy, mặc định 5"},
            },
        },
    },
]


class AgentContext:
    """Dữ liệu thật của dây hụi và ví, để tool đọc."""

    def __init__(
        self,
        history: Optional[History] = None,
        member_count: int = 0,
        contribution: int = 0,
        period: int = 0,
        current_round: int = 0,
        mode: str = "Fixed",
        received: Optional[List[str]] = None,
        paid_this_round: Optional[List[str]] = None,
        penalty_pool: int = 0,
    ):
        self.history = history
        self.member_count = member_count
        self.contribution = contribution
        self.period = period
        self.current_round = current_round
        self.mode = mode
        self.received = received or []
        self.paid_this_round = paid_this_round or []
        self.penalty_pool = penalty_pool


def run_tool(name: str, args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Chạy một tool theo tên. Trả về dict, không bao giờ raise."""
    try:
        if name == "explain_credit_score":
            if ctx.history is None:
                return {"loi": "chưa có dữ liệu ví"}
            return tools.explain_credit_score(ctx.history)

        if name == "circle_status":
            if ctx.member_count == 0:
                return {"loi": "chưa kết nối dây hụi nào"}
            return tools.circle_status(
                ctx.member_count, ctx.contribution, ctx.period,
                ctx.current_round, ctx.mode, ctx.received,
                ctx.paid_this_round, ctx.penalty_pool,
            )

        if name == "simulate_bid":
            if ctx.member_count == 0:
                return {"loi": "chưa kết nối dây hụi nào"}
            return tools.simulate_bid(
                ctx.contribution, ctx.period,
                int(args.get("bid", 0)),
                int(args.get("receive_round", 1)),
                ctx.member_count,
            )

        if name == "bid_advice":
            if ctx.member_count == 0:
                return {"loi": "chưa kết nối dây hụi nào"}
            return tools.bid_advice(
                ctx.contribution, ctx.period, ctx.member_count)

        if name == "defi_pools":
            return tools.defi_pools(int(args.get("top", 5)))

        return {"loi": f"không có tool tên '{name}'"}
    except Exception as e:
        return {"loi": f"{e.__class__.__name__}: {e}"}


# ══════════════════════════════════════════════════════════════════
# Guardrail: chống model bịa số
# ══════════════════════════════════════════════════════════════════

_NUM = re.compile(r"\d[\d.,]*")


def _extract_numbers(text: str) -> List[float]:
    """Rút mọi số trong câu trả lời. Bỏ dấu phân cách nghìn."""
    out = []
    for m in _NUM.finditer(text):
        raw = m.group(0).rstrip(".,")
        if not raw:
            continue
        # "1.000.000" → 1000000 ; "20,5" → 20.5
        if raw.count(".") >= 1 and raw.count(",") == 0:
            candidate = raw.replace(".", "")
            try:
                out.append(float(candidate))
                continue
            except ValueError:
                pass
        try:
            out.append(float(raw.replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    return out


def _numbers_are_grounded(
    answer: str, tool_results: List[Dict[str, Any]],
) -> tuple[bool, List[float]]:
    """
    Kiểm tra mọi số trong câu trả lời có xuất hiện trong tool output không.

    Cho phép: số nhỏ ≤ 100 (vòng, %, số người) và các hằng số đã biết
    (20% trần lãi, các trọng số 45/20/15/10). Đây là những con số model
    được phép nói mà không cần tool.

    Trả về (ok, danh sách số không khớp).
    """
    allowed: set[float] = set()
    _collect_numbers(tool_results, allowed)

    WHITELIST = {
        20.0,                       # trần lãi 20%/năm
        45.0, 20.0, 15.0, 10.0,     # trọng số
        500.0, 1000.0,              # thang điểm
        0.0, 1.0, 2.0, 3.0,         # đếm nhỏ / ngưỡng
        180.0,                      # ngưỡng tuổi ví (ngày)
        450.0, 150.0, 30.0,         # tham số điểm
    }

    ungrounded = []
    for n in _extract_numbers(answer):
        if n <= 100:                # số nhỏ: vòng, %, số người — chấp nhận
            continue
        if n in WHITELIST:
            continue
        if _fuzzy_in(n, allowed):
            continue
        ungrounded.append(n)

    return (len(ungrounded) == 0, ungrounded)


def _collect_numbers(obj: Any, out: set) -> None:
    """Đệ quy gom mọi số trong dict/list tool output."""
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        out.add(float(obj))
        out.add(abs(float(obj)))
    elif isinstance(obj, str):
        for m in _NUM.finditer(obj):
            raw = m.group(0).rstrip(".,")
            try:
                out.add(float(raw.replace(".", "").replace(",", ".")))
            except ValueError:
                pass


def _fuzzy_in(n: float, allowed: set) -> bool:
    """Khớp với dung sai nhỏ — model có thể làm tròn khi diễn đạt."""
    if not allowed:
        return False
    # làm tròn: 147942 → 148000 hoặc 147.9k
    for a in allowed:
        if a == 0:
            continue
        if abs(n - a) <= max(1.0, abs(a) * 0.02):
            return True
    return False


# ══════════════════════════════════════════════════════════════════
# Vòng lặp chính
# ══════════════════════════════════════════════════════════════════

def ask(question: str, ctx: AgentContext,
        history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Hỏi agent. Trả về:
      answer       : str
      toolCalls    : list tên tool đã chạy
      grounded     : bool — mọi số có nguồn gốc từ tool
      ungrounded   : list số không khớp (nếu có)
      fallback     : bool — có dùng fallback deterministic không
      error        : str nếu LLM lỗi
    """
    tool_results: List[Dict[str, Any]] = []
    called: List[str] = []

    # Nếu không có LLM, trả về câu trả lời deterministic ngay
    first = llm.chat(SYSTEM_PROMPT, question, tools=TOOL_DECLS,
                     history=history)
    if not first.get("ok") and not first.get("tool_calls"):
        return {
            "answer": _deterministic_answer(question, ctx),
            "toolCalls": [],
            "grounded": True,
            "ungrounded": [],
            "fallback": True,
            "error": first.get("error"),
        }

    text = first.get("text", "")
    calls = first.get("tool_calls", [])
    step = 0

    while calls and step < MAX_STEPS:
        step += 1
        for c in calls:
            res = run_tool(c["name"], c.get("args", {}), ctx)
            called.append(c["name"])
            tool_results.append({"tool": c["name"], "ketQua": res})

        # Đưa kết quả tool lại cho model tổng hợp
        followup = (
            f"Câu hỏi gốc: {question}\n\n"
            f"Kết quả tool (JSON):\n"
            f"{json.dumps(tool_results, ensure_ascii=False, default=str)}\n\n"
            "Hãy trả lời người dùng bằng tiếng Việt, chỉ dùng những con số "
            "có trong kết quả tool ở trên."
        )
        nxt = llm.chat(SYSTEM_PROMPT, followup, tools=TOOL_DECLS,
                       history=history)
        if not nxt.get("ok"):
            text = _compose_from_tools(tool_results)
            break
        text = nxt.get("text", "") or text
        calls = nxt.get("tool_calls", [])

    if calls and step >= MAX_STEPS:
        # Hết lượt mà model vẫn đòi thêm tool → tự tổng hợp
        text = _compose_from_tools(tool_results)

    ok, ungrounded = _numbers_are_grounded(text, tool_results)
    if not ok:
        # Model bịa số → thay bằng bản deterministic
        return {
            "answer": _compose_from_tools(tool_results),
            "toolCalls": called,
            "grounded": False,
            "ungrounded": ungrounded,
            "fallback": True,
            "error": "ungrounded_numbers_replaced",
        }

    return {
        "answer": text,
        "toolCalls": called,
        "grounded": True,
        "ungrounded": [],
        "fallback": False,
        "error": None,
    }


def _compose_from_tools(results: List[Dict[str, Any]]) -> str:
    """Ghép câu trả lời chỉ từ tool output — không có model."""
    if not results:
        return ("Tôi chưa có dữ liệu để trả lời. Hãy kết nối ví và dây hụi "
                "trước.")
    parts = []
    for r in results:
        res = r["ketQua"]
        if "loi" in res:
            parts.append(f"({r['tool']}: {res['loi']})")
            continue
        if r["tool"] == "explain_credit_score":
            parts.append(
                f"Điểm uy tín: {res['diem']}/1000, hạng {res['hangMuc']}. "
                + " ".join(res.get("lyDo", []))
            )
        elif r["tool"] == "circle_status":
            parts.append(
                f"Dây {res['soNguoi']} người, đang kỳ {res['kyHienTai']}/"
                f"{res['tongSoKy']}, {res['daNhanPot']} người đã nhận pot, "
                f"{res['chuaNhanPot']} người chưa nhận. "
                + " ".join(res.get("nhanXet", []))
            )
        elif r["tool"] == "simulate_bid":
            parts.append(res.get("dienGiai", ""))
        elif r["tool"] == "bid_advice":
            lines = [m["dienGiai"] for m in res.get("cacMuc", [])
                     if m.get("dienGiai")]
            parts.append(" ".join(lines) + " " + res.get("luuY", ""))
        elif r["tool"] == "defi_pools":
            top = res.get("pools", [])[:3]
            if top:
                parts.append(
                    "Pool Avalanche: "
                    + "; ".join(f"{p['pool']} {p['apy']}% APY"
                                for p in top)
                    + ". " + res.get("luuY", "")
                )
            else:
                parts.append("Không lấy được dữ liệu pool.")
    return "\n\n".join(p for p in parts if p)


def _deterministic_answer(question: str, ctx: AgentContext) -> str:
    """
    Khi không có LLM: vẫn trả lời hữu ích bằng tool, không có văn phong.
    Chọn tool theo từ khoá để không cần model.
    """
    q = question.lower()
    picks = []
    if any(k in q for k in ("điểm", "uy tín", "score", "tín dụng")):
        picks.append("explain_credit_score")
    if any(k in q for k in ("kêu giá", "bid", "đấu giá", "kêu")):
        picks.append("bid_advice")
    if any(k in q for k in ("yield", "lãi suất", "gửi", "pool", "apy")):
        picks.append("defi_pools")
    if any(k in q for k in ("chiến lược", "tình hình", "trạng thái", "dây")):
        picks.append("circle_status")
    if not picks:
        picks = ["circle_status", "explain_credit_score"]

    results = [{"tool": n, "ketQua": run_tool(n, {}, ctx)} for n in picks]
    body = _compose_from_tools(results)
    return (
        "_(Chế độ không có AI: đây là số liệu trực tiếp từ hợp đồng.)_\n\n"
        + body
    )
