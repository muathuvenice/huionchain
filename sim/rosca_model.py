"""
Ban mo phong tham chieu (reference model) cho hui on-chain.

Day la DAC TA SO HOC cua contract RoscaCircle.sol. Moi cong thuc o day
phai khop 1-1 voi Solidity. Chay `python3 rosca_model.py` de tu kiem tra.

Mo hinh ke toan
---------------
n thanh vien, moi vong gop A, co n vong, moi vong mot nguoi nhan.

  Nguoi DA nhan hui ("hui chet") dong:   A
  Nguoi CHUA nhan hui ("hui song") dong: A - d   (d = gia thang vong nay)
  Nguoi THANG vong nay KHONG dong gi ca.

  pot(vong) = tong tat ca cac khoan dong trong vong do
             = (n-1)*(A-d) + (so nguoi da nhan truoc do)*d

  Nguoi thang nhan dung pot(vong).

Vi sao hui chet dong dung A chu khong phai A+d:
  Neu hui chet dong A+d thi tong tien thu moi vong se lon hon tong tien
  tra ra, tuc la he thong TU SINH RA TIEN - bat kha thi on-chain. Cach
  dung la: nguoi nhan som "tra lai" bang viec nhan pot bi chiet khau.
  Kiem chung: vong 1, n=10, d=100k, A=1tr -> pot = 9*(1tr-100k) =
  8.100.000. Nguoi thang sau do dong 1tr x 9 vong = 9.000.000.
  Net = 8.100.000 - 9.000.000 = -900.000 = -9d. Dung bang tien lai
  phai tra cho 9 nguoi con lai. He thong zero-sum theo tung vong.

Kinh te: nguoi nhan som tra lai (net am), nguoi nhan muon huong lai
(net duong). Tong net cua tat ca = 0.

Tran lai suat
-------------
Gia keu d la lai tra them moi KY tren mot don vi gop A. Quy ra nam:

    apr = (d / A) * (YEAR / period)

Bo luat Dan su 2015 Dieu 468 chan tran 20%/nam, nen:

    d <= A * 20% * period / YEAR

Contract cuong che dung bat dang thuc nay trong `_maxBid()`.
"""
from __future__ import annotations

from dataclasses import dataclass

BPS = 10_000
MAX_APR_BPS = 2_000          # 20%/nam
YEAR = 365 * 24 * 3600


def max_bid(contribution: int, period: int) -> int:
    """Gia keu toi da cho mot ky, theo tran 20%/nam."""
    return contribution * MAX_APR_BPS * period // (BPS * YEAR)


def bid_to_apr(contribution: int, period: int, bid: int) -> float:
    """Quy doi gia keu ra APR de hien thi tren dashboard."""
    if contribution == 0:
        return 0.0
    return (bid / contribution) * (YEAR / period) * 100.0


@dataclass
class Member:
    addr: str
    joined: int = 0
    received_round: int | None = None
    bid: int = 0
    paid_total: int = 0
    received_total: int = 0
    late_count: int = 0
    defaulted_round: int | None = None
    deposit: int = 0
    slashed: int = 0


class RoscaModel:
    def __init__(self, n: int, contribution: int, period: int,
                 deposit_mult: int = 100):
        assert n >= 2 and contribution > 0
        self.n = n
        self.A = contribution
        self.period = period
        self.deposit = contribution * deposit_mult // 100
        self.members: list[Member] = []
        self.rounds: list[dict] = []
        self.pool = 0
        self.shortfall = 0

    def join(self, addr: str) -> Member:
        assert len(self.members) < self.n, "day da du nguoi"
        m = Member(addr=addr, joined=len(self.members), deposit=self.deposit)
        self.members.append(m)
        self.pool += self.deposit
        return m

    def payment_due(self, m: Member, bid_this_round: int) -> int:
        """So tien thanh vien phai dong o vong nay (chua gom phat tre)."""
        if m.defaulted_round is not None:
            return 0
        if m.received_round is not None:
            return self.A
        return self.A - bid_this_round

    def run_round(self, round_idx: int, bid_this_round: int,
                  winner_idx: int, defaulters: tuple[int, ...] = ()) -> dict:
        assert len(self.rounds) == round_idx
        collected = 0
        rows = []

        for i, m in enumerate(self.members):
            if i == winner_idx:
                rows.append((m.addr, 0, 0, "winner"))
                continue
            due = self.payment_due(m, bid_this_round)
            if i in defaulters:
                covered = min(due, m.deposit - m.slashed)
                m.slashed += covered
                self.pool -= covered
                self.shortfall += due - covered
                m.defaulted_round = round_idx
                collected += covered
                rows.append((m.addr, due, covered, "default"))
                continue
            m.paid_total += due
            collected += due
            rows.append((m.addr, due, due, "paid"))

        pot = collected
        w = self.members[winner_idx]
        w.received_round = round_idx
        w.bid = bid_this_round
        w.received_total += pot
        self.pool += pot          # thu truoc
        self.pool -= pot          # tra ngay

        rec = {"round": round_idx, "bid": bid_this_round, "winner": w.addr,
               "pot": pot, "rows": rows,
               "apr": bid_to_apr(self.A, self.period, bid_this_round)}
        self.rounds.append(rec)
        return rec

    def close(self) -> dict:
        refunds, total = {}, 0
        for m in self.members:
            left = m.deposit - m.slashed
            refunds[m.addr] = left
            total += left
            self.pool -= left
        return {"refunds": refunds, "total_refunded": total,
                "pool_left": self.pool, "shortfall": self.shortfall}

    def net(self, i: int) -> int:
        m = self.members[i]
        return m.received_total - m.paid_total

    def invariant_ok(self) -> bool:
        """Tong net cua moi nguoi = -shortfall (thieu hut do bung)."""
        return sum(self.net(i) for i in range(self.n)) == -self.shortfall
