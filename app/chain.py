"""
Lớp đọc/ghi contract. Tách khỏi UI để test được mà không cần Streamlit.

Mọi hàm ở đây nhận `w3` và `address` tường minh, không đọc biến toàn cục,
nhờ vậy test có thể chạy trên một node giả lập.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.contract_abi import (ROSCA_CIRCLE_ABI, ROSCA_FACTORY_ABI,
                              ERC20_ABI)

FUJI_CHAIN_ID = 43113
FUJI_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
FUJI_EXPLORER = "https://subnets-test.avax.network/c-chain"

# USDC chính thức trên Fuji. Xác nhận lại trước khi deploy thật.
USDC_FUJI = "0x5425890298aed601595a70AB815c96711a31Bc65"

MODE_NAMES = {0: "Cố định", 1: "Đấu giá"}
PHASE_NAMES = {0: "Đang mở", 1: "Đấu giá kín", 2: "Đang thu tiền", 3: "Đã đóng"}


@dataclass
class CircleView:
    address: str
    mode: int
    phase: int
    member_count: int
    contribution: int
    deposit: int
    current_round: int
    max_bid: int
    total_pool: int
    deposits_held: int
    penalty_pool: int
    shortfall: int
    period: int = 30 * 86400

    @property
    def mode_name(self) -> str:
        return MODE_NAMES.get(self.mode, "?")

    @property
    def phase_name(self) -> str:
        return PHASE_NAMES.get(self.phase, "?")


@dataclass
class MemberView:
    address: str
    index: int
    paid_total: int
    received_total: int
    won_round: Optional[int]
    deposit_left: int
    late_count: int
    default_round: Optional[int]
    amount_due: int

    @property
    def net(self) -> int:
        return self.received_total - self.paid_total

    @property
    def status(self) -> str:
        if self.default_round:
            return f"Cáo (vòng {self.default_round})"
        if self.won_round:
            return f"Đã nhận (vòng {self.won_round})"
        return "Chưa nhận"


def _c(w3, address, abi):
    return w3.eth.contract(address=w3.to_checksum_address(address), abi=abi)


def read_circle(w3, address: str) -> CircleView:
    c = _c(w3, address, ROSCA_CIRCLE_ABI)
    return CircleView(
        address=address,
        mode=c.functions.mode().call(),
        phase=c.functions.phase().call(),
        member_count=c.functions.memberCount().call(),
        contribution=c.functions.contribution().call(),
        deposit=c.functions.deposit().call(),
        current_round=c.functions.currentRound().call(),
        max_bid=c.functions.maxBid().call(),
        total_pool=c.functions.totalPool().call(),
        deposits_held=c.functions.depositsHeld().call(),
        penalty_pool=c.functions.penaltyPool().call(),
        shortfall=c.functions.shortfall().call(),
        period=c.functions.period().call(),
    )


def read_members(w3, address: str) -> list[MemberView]:
    c = _c(w3, address, ROSCA_CIRCLE_ABI)
    n = c.functions.membersLength().call()
    out = []
    for i in range(n):
        addr = c.functions.members(i).call()
        paid, recv, won1, dep_left, late, def1 = \
            c.functions.memberSnapshot(addr).call()
        due = c.functions.amountDue(addr).call()
        out.append(MemberView(
            address=addr,
            index=i,
            paid_total=paid,
            received_total=recv,
            won_round=won1 or None,
            deposit_left=dep_left,
            late_count=late,
            default_round=def1 or None,
            amount_due=due,
        ))
    return out


def read_rounds(w3, address: str) -> list[dict]:
    c = _c(w3, address, ROSCA_CIRCLE_ABI)
    n = c.functions.roundsLength().call()
    rows = []
    for k in range(n):
        receiver, bid, pot, paid_count, commit_dl, pay_dl, settled = \
            c.functions.roundSnapshot(k).call()
        rows.append({
            "round": k + 1,
            "receiver_index": receiver,
            "bid": bid,
            "pot": pot,
            "paid_count": paid_count,
            "commit_deadline": commit_dl,
            "pay_deadline": pay_dl,
            "settled": settled,
        })
    return rows


def read_history(w3, address: str, from_block: int = 0) -> list[dict]:
    """
    Đọc toàn bộ sự kiện của một dây hụi, dựng thành bảng lịch sử.
    Dùng cho cả dashboard và module credit score.
    """
    c = _c(w3, address, ROSCA_CIRCLE_ABI)
    events = []

    def pull(name, fmt):
        ev = getattr(c.events, name)
        try:
            logs = ev.create_filter(fromBlock=from_block,
                                    toBlock="latest").get_all_entries()
        except Exception:
            return
        for lg in logs:
            try:
                events.append(fmt(lg))
            except Exception:
                continue

    pull("Joined", lambda l: {
        "type": "join", "block": l["blockNumber"],
        "member": l["args"]["member"], "index": l["args"]["index"],
    })
    pull("PaidIn", lambda l: {
        "type": "pay", "block": l["blockNumber"],
        "member": l["args"]["member"], "round": l["args"]["roundIdx"],
        "due": l["args"]["due"], "fee": l["args"]["fee"],
    })
    pull("BidCommitted", lambda l: {
        "type": "commit", "block": l["blockNumber"],
        "member": l["args"]["member"], "round": l["args"]["roundIdx"],
    })
    pull("BidRevealed", lambda l: {
        "type": "reveal", "block": l["blockNumber"],
        "member": l["args"]["member"], "round": l["args"]["roundIdx"],
        "bid": l["args"]["bid"],
    })
    pull("CircleSettled", lambda l: {
        "type": "settle", "block": l["blockNumber"],
        "round": l["args"]["roundIdx"], "receiver": l["args"]["receiver"],
        "bid": l["args"]["bid"], "pot": l["args"]["pot"],
    })
    pull("Payout", lambda l: {
        "type": "payout", "block": l["blockNumber"],
        "receiver": l["args"]["receiver"], "round": l["args"]["roundIdx"],
        "pot": l["args"]["pot"],
    })
    pull("MemberDefaulted", lambda l: {
        "type": "default", "block": l["blockNumber"],
        "member": l["args"]["member"], "round": l["args"]["roundIdx"],
        "covered": l["args"]["covered"], "short": l["args"]["short"],
    })

    events.sort(key=lambda e: (e["block"], e["type"]))
    return events


def build_tx(w3, fn, sender: str, gas: int = 3_000_000) -> dict:
    """Dựng transaction dict để ví ký (MetaMask / Core)."""
    return fn.build_transaction({
        "from": w3.to_checksum_address(sender),
        "nonce": w3.eth.get_transaction_count(sender),
        "gas": gas,
        "chainId": FUJI_CHAIN_ID,
    })


def fmt_usdc(amount: int, decimals: int = 6) -> str:
    return f"{amount / 10 ** decimals:,.2f}"


def etherscan_link(tx_hash: str) -> str:
    return f"{FUJI_EXPLORER}/tx/{tx_hash}"
