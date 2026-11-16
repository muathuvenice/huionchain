"""
Cầu nối giữa dữ liệu on-chain (app/chain.py) và AI agent (ai/agent.py).
Tách khỏi app/main.py để unit test được mà không cần Streamlit.
"""
from __future__ import annotations

from typing import Dict, List

from ai.agent import AgentContext
from ai.credit_score import History
from app.chain import CircleView, read_circle, read_history


def build_agent_context_from_data(
    c: CircleView,
    events: List[Dict],
    me: str = "",
) -> AgentContext:
    """Dựng AgentContext từ CircleView và danh sách sự kiện đã đọc."""
    paid = [e for e in events if e["type"] == "pay"]
    defaulted = [e for e in events if e["type"] == "default"]
    revealed = [e for e in events if e["type"] == "reveal"]
    payouts = [e for e in events if e["type"] == "payout"]

    received = [e["receiver"] for e in payouts]
    paid_this = [e["member"] for e in paid
                 if e.get("round") == c.current_round]

    history = None
    if me:
        me_low = me.lower()
        mine_paid = [e for e in paid if e["member"].lower() == me_low]
        mine_def = [e for e in defaulted if e["member"].lower() == me_low]
        mine_rev = [e for e in revealed if e["member"].lower() == me_low]
        late = sum(1 for e in mine_paid if e.get("fee", 0) > 0)
        history = History(
            address=me,
            roundsJoined=len(mine_paid) + len(mine_def),
            paidOnTime=len(mine_paid) - late,
            paidLate=late,
            defaults=len(mine_def),
            bidsWon=len(mine_rev),
            avgBidRatio=(
                sum(e["bid"] for e in mine_rev) / (len(mine_rev) * c.max_bid)
                if mine_rev and c.max_bid else 0.0
            ),
            circlesDone=0,
            walletAgeDays=0,
        )

    return AgentContext(
        history=history,
        member_count=c.member_count,
        contribution=c.contribution,
        period=c.period,
        current_round=c.current_round,
        mode=c.mode_name,
        received=received,
        paid_this_round=paid_this,
        penalty_pool=c.penalty_pool,
    )


def build_agent_context(w3, addr: str, me: str = "") -> AgentContext:
    """
    Gom dữ liệu thật từ contract thành AgentContext cho agent.
    Không có kết nối thì trả về context rỗng — agent sẽ tự nói là thiếu dữ liệu.
    """
    if not (w3 and addr):
        return AgentContext()

    try:
        c = read_circle(w3, addr)
        events = read_history(w3, addr)
    except Exception:
        return AgentContext()

    return build_agent_context_from_data(c, events, me)
