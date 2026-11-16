"""
Hụi On-Chain — giao diện Streamlit.

Chạy:
    streamlit run app/main.py

Thiết kế: mọi phép tính và truy vấn nằm trong app/chain.py và
ai/credit_score.py. File này chỉ dựng giao diện. Nhờ vậy phần logic
test được mà không cần Streamlit.
"""
from __future__ import annotations

import hashlib
import os
import time

import streamlit as st

from app.chain import (FUJI_CHAIN_ID, FUJI_RPC, MODE_NAMES, PHASE_NAMES,
                       USDC_FUJI, fmt_usdc, read_circle, read_history,
                       read_members, read_rounds)
from ai.credit_score import History, score
from app.agent_bridge import build_agent_context
from ai import agent as _agent

st.set_page_config(page_title="Hụi On-Chain", page_icon="🪙", layout="wide")

CIRCLE_KEY = "circle_address"


def _w3():
    """Kết nối Web3. Trả None nếu chưa cài web3 (chế độ xem offline)."""
    try:
        from web3 import Web3
    except ImportError:
        return None
    rpc = st.session_state.get("rpc", FUJI_RPC)
    return Web3(Web3.HTTPProvider(rpc))


def _hash_bid(bid: int, salt: str, address: str, round_idx: int) -> str:
    """
    Cam kết giá kêu. Phải khớp CHÍNH XÁC với Solidity:
        keccak256(abi.encode(bid, salt, msg.sender, currentRound))
    Dùng eth_abi để encode đúng kiểu (uint256, bytes32, address, uint16).
    """
    from eth_abi import encode
    payload = encode(["uint256", "bytes32", "address", "uint16"],
                     [bid, bytes.fromhex(salt.lstrip("0x").ljust(64, "0")[:64]),
                      address, round_idx])
    from eth_utils import keccak
    return "0x" + keccak(payload).hex()


def sidebar():
    st.sidebar.title("Hụi On-Chain")
    st.sidebar.caption("ROSCA trên Avalanche Fuji")
    network = st.sidebar.selectbox("Mạng", ["Fuji Testnet"], index=0)
    if network:
        st.sidebar.code(FUJI_RPC, language=None)
    st.sidebar.divider()
    addr = st.sidebar.text_input("Địa chỉ dây hụi", key=CIRCLE_KEY,
                                 placeholder="0x...")
    st.sidebar.divider()
    st.sidebar.caption(
        f"USDC Fuji: `{USDC_FUJI[:6]}…{USDC_FUJI[-4:]}`\n\n"
        "Mọi giao dịch đều cần bạn ký trong ví — "
        "contract không tự chuyển tiền thay bạn."
    )
    return addr


def tab_overview(w3, addr):
    st.subheader("Tổng quan dây hụi")
    if not addr:
        st.info("Nhập địa chỉ dây hụi ở thanh bên để bắt đầu.")
        return
    if w3 is None:
        st.warning("Chưa cài `web3`. Chạy: `pip install web3` "
                   "(cần mạng để cài).")
        return

    try:
        c = read_circle(w3, addr)
        members = read_members(w3, addr)
    except Exception as e:
        st.error(f"Không đọc được contract: {e}")
        return

    col = st.columns(5)
    col[0].metric("Chế độ", c.mode_name)
    col[1].metric("Trạng thái", c.phase_name)
    col[2].metric("Vòng", f"{c.current_round + 1}/{c.member_count}")
    col[3].metric("Góp mỗi kỳ", fmt_usdc(c.contribution))
    col[4].metric("Ký quỹ", fmt_usdc(c.deposit))

    col2 = st.columns(4)
    col2[0].metric("Trong contract", fmt_usdc(c.total_pool))
    col2[1].metric("Ký quỹ đang giữ", fmt_usdc(c.deposits_held))
    col2[2].metric("Quỹ phạt", fmt_usdc(c.penalty_pool))
    col2[3].metric("Thiếu hụt (cáo)", fmt_usdc(c.shortfall))

    if c.shortfall > 0:
        st.error(
            f"Đã có {fmt_usdc(c.shortfall)} USDC thiếu hụt do có người cáo. "
            "Khoản này được ghi công khai, không giấu."
        )

    st.divider()
    st.markdown("#### Thành viên")
    rows = []
    for m in members:
        rows.append({
            "#": m.index + 1,
            "Ví": f"{m.address[:6]}…{m.address[-4:]}",
            "Trạng thái": m.status,
            "Đã đóng": fmt_usdc(m.paid_total),
            "Đã nhận": fmt_usdc(m.received_total),
            "Lãi/lỗ": fmt_usdc(m.net),
            "Ký quỹ còn": fmt_usdc(m.deposit_left),
            "Trễ": m.late_count,
            "Kỳ này phải đóng": fmt_usdc(m.amount_due),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def tab_pay(w3, addr):
    st.subheader("Đóng hụi kỳ này")
    if not (w3 and addr):
        st.info("Cần địa chỉ dây hụi và kết nối mạng.")
        return

    try:
        c = read_circle(w3, addr)
        members = read_members(w3, addr)
    except Exception as e:
        st.error(str(e))
        return

    me = st.text_input("Ví của bạn", placeholder="0x...")
    if not me:
        return

    mv = next((m for m in members
               if m.address.lower() == me.lower()), None)
    if mv is None:
        st.warning("Ví này chưa tham gia dây hụi.")
        return

    st.metric("Bạn phải đóng kỳ này", fmt_usdc(mv.amount_due))
    if mv.amount_due == 0:
        st.success("Kỳ này bạn là người nhận hụi — không phải đóng.")
        return

    if st.button("Ký giao dịch đóng hụi", type="primary"):
        with st.spinner("Đang dựng giao dịch…"):
            st.session_state["pending"] = {
                "to": addr, "fn": "payIn", "args": [],
            }
        st.success(
            "Đã dựng giao dịch. Mở ví để ký — "
            "bước ký nằm ở ví, không nằm ở app này."
        )


def tab_bidding(w3, addr):
    st.subheader("Đấu giá kín")
    if not (w3 and addr):
        return

    try:
        c = read_circle(w3, addr)
    except Exception as e:
        st.error(str(e))
        return

    if c.mode != 1:
        st.info("Dây này chia theo thứ tự cố định, không đấu giá.")
        return

    st.metric("Trần giá kêu kỳ này", fmt_usdc(c.max_bid))
    st.caption(
        "Trần này là 20%/năm trên khoản góp, theo Bộ luật Dân sự 2015 "
        "Điều 468. Contract từ chối mọi giá kêu vượt trần — không cắt "
        "âm thầm, mà revert."
    )

    me = st.text_input("Ví của bạn", key="bid_me", placeholder="0x...")
    if not me:
        return

    st.markdown("**Bước 1 — Cam kết (không ai thấy giá)**")
    bid = st.number_input("Giá kêu (USDC)", min_value=0.0,
                          max_value=c.max_bid / 1e6, step=0.01)
    salt = st.text_input("Chuỗi bí mật (tự nghĩ, ghi nhớ)",
                         value=hashlib.sha256(os.urandom(16)).hexdigest()[:16])
    if st.button("Cam kết giá"):
        try:
            h = _hash_bid(int(bid * 1e6), salt, me, c.current_round)
            st.session_state["commit_hash"] = h
            st.code(h, language=None)
            st.success(
                "Gửi `commitBid(hash)` bằng ví. Lưu chuỗi bí mật — "
                "mất là mất tiền ký quỹ."
            )
        except Exception as e:
            st.error(f"Không tính được hash: {e}")

    st.markdown("**Bước 2 — Mở giá (sau khi hết hạn cam kết)**")
    if st.button("Mở giá"):
        st.info(
            "Gửi `revealBid(bid, salt)`. Nếu reveal sớm hơn hạn cam kết, "
            "contract sẽ revert — đó là điều kiện để đấu giá thực sự kín."
        )

    st.divider()
    if st.button("Chốt vòng (ai cũng gọi được)"):
        st.info("Gọi `settle()` sau khi hết cửa sổ mở giá.")


def tab_history(w3, addr):
    st.subheader("Lịch sử giao dịch")
    if not (w3 and addr):
        return
    try:
        events = read_history(w3, addr)
    except Exception as e:
        st.error(str(e))
        return

    if not events:
        st.info("Chưa có sự kiện nào.")
        return

    labels = {"join": "Tham gia", "pay": "Đóng hụi", "commit": "Cam kết giá",
              "reveal": "Mở giá", "settle": "Chốt vòng",
              "payout": "Nhận hụi", "default": "Cáo"}
    rows = []
    for e in events:
        row = {"Block": e["block"], "Loại": labels.get(e["type"], e["type"])}
        if "member" in e:
            row["Ví"] = f"{e['member'][:6]}…{e['member'][-4:]}"
        if "round" in e:
            row["Vòng"] = e["round"] + 1
        if e["type"] == "pay":
            row["Số tiền"] = fmt_usdc(e["due"])
            row["Phạt trễ"] = fmt_usdc(e["fee"])
        if e["type"] in ("reveal", "settle"):
            row["Giá kêu"] = fmt_usdc(e["bid"])
        if e["type"] in ("settle", "payout"):
            row["Pot"] = fmt_usdc(e["pot"])
        if e["type"] == "default":
            row["Ký quỹ bù"] = fmt_usdc(e["covered"])
            row["Thiếu"] = fmt_usdc(e["short"])
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True)


def tab_score(w3, addr):
    st.subheader("Điểm uy tín")
    st.caption(
        "Điểm tính bằng công thức cố định trên dữ liệu on-chain — "
        "không dùng mô hình ngôn ngữ. Ai cũng tính lại được từ log."
    )
    if not (w3 and addr):
        return

    me = st.text_input("Ví cần chấm", key="score_me", placeholder="0x...")
    if not me:
        return

    try:
        events = read_history(w3, addr)
        members = read_members(w3, addr)
    except Exception as e:
        st.error(str(e))
        return

    paid = [e for e in events if e["type"] == "pay"]
    defaulted = [e for e in events if e["type"] == "default"]
    revealed = [e for e in events if e["type"] == "reveal"]

    mine_paid = [e for e in paid if e["member"].lower() == me.lower()]
    mine_def = [e for e in defaulted if e["member"].lower() == me.lower()]
    mine_rev = [e for e in revealed if e["member"].lower() == me.lower()]

    late = sum(1 for e in mine_paid if e.get("fee", 0) > 0)
    max_bid = read_circle(w3, addr).max_bid

    h = History(
        address=me,
        roundsJoined=len(mine_paid) + len(mine_def),
        paidOnTime=len(mine_paid) - late,
        paidLate=late,
        defaults=len(mine_def),
        bidsWon=len(mine_rev),
        avgBidRatio=(sum(e["bid"] for e in mine_rev) /
                     (len(mine_rev) * max_bid) if mine_rev and max_bid else 0.0),
        circlesDone=0,
        walletAgeDays=0,
        hasEduKyc=False,
    )
    r = score(h)

    col = st.columns(3)
    col[0].metric("Điểm", r.score)
    col[1].metric("Hạng", r.band)
    col[2].metric("Trần góp đề xuất", fmt_usdc(r.maxContribution))

    st.markdown("**Vì sao có điểm này**")
    for reason in r.reasons:
        st.write(f"· {reason}")

    with st.expander("Thành phần điểm (để kiểm toán)"):
        st.json(r.components)
        st.caption(
            "Điểm chỉ là gợi ý. Contract KHÔNG chặn ai dựa trên điểm — "
            "đó là lựa chọn có chủ đích: chấm điểm sai không được phép "
            "tước quyền tự quyết của người dùng."
        )


def _build_agent_context(w3, addr, me: str):
    return build_agent_context(w3, addr, me)


def tab_assistant(w3, addr):
    st.subheader("Trợ lý AI")
    st.caption(
        "Trợ lý đọc dữ liệu on-chain qua bộ công cụ cố định rồi diễn giải. "
        "Mọi con số đều lấy từ hợp đồng — nếu model nói một số không có "
        "trong dữ liệu, câu trả lời đó bị thay bằng bản tính trực tiếp."
    )

    if "chat_log" not in st.session_state:
        st.session_state.chat_log = []

    me = st.text_input("Ví của bạn (tuỳ chọn)", key="agent_me",
                       placeholder="0x... — để trống nếu chỉ hỏi về dây")
    provider_ok = bool(os.environ.get("GEMINI_API_KEY")
                       or os.environ.get("GOOGLE_API_KEY"))
    if not provider_ok:
        st.info(
            "Chưa đặt `GEMINI_API_KEY` — trợ lý vẫn trả lời được bằng số liệu "
            "trực tiếp, nhưng không có phần diễn giải tự nhiên. "
            "Lấy key miễn phí tại aistudio.google.com/app/apikey."
        )

    # Gợi ý câu hỏi
    st.markdown("**Hỏi nhanh**")
    suggestions = [
        "Điểm uy tín của tôi thế nào?",
        "Nên kêu giá bao nhiêu?",
        "Tình hình dây hụi này ra sao?",
        "Nhận sớm hay nhận muộn có lợi hơn?",
        "Tiền nhàn rỗi gửi đâu được?",
    ]
    cols = st.columns(len(suggestions))
    picked = None
    for i, s in enumerate(suggestions):
        if cols[i].button(s, key=f"sug_{i}", use_container_width=True):
            picked = s

    question = st.chat_input("Hỏi về dây hụi, điểm uy tín, hoặc mức kêu giá…")
    question = picked or question

    # Hiển thị lịch sử chat
    for turn in st.session_state.chat_log:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    if question:
        st.session_state.chat_log.append(
            {"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Đang đọc dữ liệu on-chain…"):
                ctx = _build_agent_context(w3, addr, me)
                history = [
                    {"role": t["role"], "content": t["content"]}
                    for t in st.session_state.chat_log[:-1][-6:]
                ]
                res = _agent.ask(question, ctx, history=history)

            st.markdown(res["answer"])

            if res["toolCalls"]:
                with st.expander("Công cụ đã dùng"):
                    st.write(", ".join(res["toolCalls"]))
            if res["fallback"] and res.get("error") == \
                    "ungrounded_numbers_replaced":
                st.caption(
                    "⚠️ Model đưa ra con số không khớp dữ liệu hợp đồng, nên "
                    "câu trả lời đã được thay bằng bản tính trực tiếp. "
                    "Đây là guardrail hoạt động đúng."
                )

        st.session_state.chat_log.append(
            {"role": "assistant", "content": res["answer"]})

    if st.session_state.chat_log and st.button("Xoá hội thoại"):
        st.session_state.chat_log = []
        st.rerun()


def main():
    addr = sidebar()
    w3 = _w3()

    st.title("Hụi On-Chain")
    st.caption(
        "Quỹ nằm trong contract, không nằm trong tay chủ hụi. "
        "Mọi dòng tiền đều công khai."
    )

    t1, t2, t3, t4, t5, t6 = st.tabs(
        ["Tổng quan", "Đóng hụi", "Đấu giá", "Lịch sử", "Điểm uy tín",
         "Trợ lý AI"]
    )
    with t1:
        tab_overview(w3, addr)
    with t2:
        tab_pay(w3, addr)
    with t3:
        tab_bidding(w3, addr)
    with t4:
        tab_history(w3, addr)
    with t5:
        tab_score(w3, addr)
    with t6:
        tab_assistant(w3, addr)


if __name__ == "__main__":
    main()
