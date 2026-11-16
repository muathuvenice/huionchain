"""
Chấm điểm uy tín (credit score) cho hụi on-chain.

VÌ SAO KHÔNG DÙNG LLM Ở ĐÂY
---------------------------
Điểm uy tín quyết định ai được vào dây hụi và ai được duyệt. Nếu để một
mô hình ngôn ngữ sinh ra con số đó:

  - Không tái lập được: cùng một ví, hỏi hai lần có thể ra hai điểm khác.
  - Không giải thích được cho người bị từ chối.
  - Không kiểm toán được: không ai chứng minh được điểm đó đúng.

Với tài chính, đó là ba lỗi chí mạng. Nên điểm ở đây là **công thức
cố định trên dữ liệu on-chain**, ai cũng tính lại được từ log của
contract. LLM (nếu dùng) chỉ viết lời giải thích, không đụng vào số.

DỮ LIỆU ĐẦU VÀO (lấy từ sự kiện của RoscaCircle)
------------------------------------------------
  roundsJoined   : số vòng đã tham gia
  paidOnTime     : số kỳ đóng đúng hạn
  paidLate       : số kỳ đóng trễ
  defaults       : số lần cáo
  bidsWon        : số vòng thắng đấu giá
  avgBidRatio    : giá kêu trung bình / trần giá kêu (0..1)
  circlesDone    : số dây đã chơi xong trọn vẹn
  walletAgeDays  : tuổi ví tính từ giao dịch đầu tiên

ĐIỂM
----
  0..1000. Mới hoàn toàn = 500 (trung tính, KHÔNG phải 0 — vì 0 sẽ
  khoá vĩnh viễn người mới, đúng bài toán cold start mà dự án nêu).
"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class History:
    """Dữ liệu thô rút ra từ log on-chain của một ví."""
    address: str
    roundsJoined: int = 0
    paidOnTime: int = 0
    paidLate: int = 0
    defaults: int = 0
    bidsWon: int = 0
    avgBidRatio: float = 0.0      # 0..1
    circlesDone: int = 0
    walletAgeDays: int = 0
    hasEduKyc: bool = False       # bonus: xác thực thẻ sinh viên

    @property
    def totalPayments(self) -> int:
        return self.paidOnTime + self.paidLate


@dataclass
class ScoreResult:
    score: int
    band: str
    maxContribution: int          # trần góp mỗi kỳ đề xuất (đơn vị token)
    reasons: list                 # lý do, để hiển thị cho người dùng
    components: dict              # điểm từng phần, để kiểm toán


# Trọng số. Tổng = 1.0
W_REPAYMENT = 0.45      # trả đúng hạn - quan trọng nhất
W_COMPLETION = 0.20     # chơi hết dây, không bỏ giữa chừng
W_EXPERIENCE = 0.15     # số vòng đã tham gia
W_BID_BEHAVIOUR = 0.10  # kêu giá có kỷ luật, không hớt váng
W_AGE = 0.10            # tuổi ví

BASE_SCORE = 500
MAX_SCORE = 1000


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score(history: History, base_unit: int = 1_000_000) -> ScoreResult:
    """
    Tính điểm uy tín 0..1000.

    Nguyên tắc chuẩn hoá: chỉ những thành phần CÓ dữ liệu mới được tính,
    và trọng số được chia lại theo đúng những thành phần đó. Nhờ vậy ví
    mới tinh (không có dữ liệu gì) rơi đúng vào BASE_SCORE = 500, thay vì
    bị kéo xuống thấp chỉ vì thiếu lịch sử. Đây là điều kiện để không
    lặp lại bài toán cold start mà dự án đang muốn giải.

    Cáo (default) là yếu tố gần như phủ quyết: trừ thẳng điểm, vì trong
    tín dụng, một lần bùng nợ nói nhiều hơn hai mươi kỳ trả đúng hẹn.
    """
    reasons = []
    parts = []          # (trọng số, giá trị, có dữ liệu?)

    # ── 1. Tỉ lệ trả đúng hạn (quan trọng nhất) ────────────────────
    if history.totalPayments == 0:
        parts.append((W_REPAYMENT, 0.5, False))
        reasons.append("chưa có lịch sử đóng hụi")
    else:
        repayment = history.paidOnTime / history.totalPayments
        parts.append((W_REPAYMENT, repayment, True))
        if history.paidLate:
            reasons.append(f"trễ {history.paidLate} kỳ trên "
                           f"{history.totalPayments} kỳ đã đóng")
        else:
            reasons.append(f"đóng đúng hạn {history.paidOnTime}/"
                           f"{history.totalPayments} kỳ")

    # ── 2. Hoàn thành dây ──────────────────────────────────────────
    if history.defaults > 0:
        parts.append((W_COMPLETION, 0.0, True))
        reasons.append(f"đã cáo {history.defaults} lần")
    elif history.circlesDone == 0:
        parts.append((W_COMPLETION, 0.5, False))
    else:
        parts.append((W_COMPLETION, _clamp(history.circlesDone / 3.0), True))
        reasons.append(f"hoàn thành trọn {history.circlesDone} dây")

    # ── 3. Kinh nghiệm ─────────────────────────────────────────────
    if history.roundsJoined == 0:
        parts.append((W_EXPERIENCE, 0.5, False))
    else:
        parts.append((W_EXPERIENCE, _clamp(history.roundsJoined / 20.0), True))

    # ── 4. Hành vi đấu giá ─────────────────────────────────────────
    # Kêu sát trần = hớt váng, cần tiền gấp -> dấu hiệu rủi ro.
    if history.bidsWon == 0:
        parts.append((W_BID_BEHAVIOUR, 0.5, False))
    else:
        parts.append((W_BID_BEHAVIOUR, _clamp(1.0 - history.avgBidRatio), True))
        if history.avgBidRatio > 0.7:
            reasons.append(f"kêu giá sát trần "
                           f"({history.avgBidRatio:.0%} mức tối đa)")

    # ── 5. Tuổi ví ─────────────────────────────────────────────────
    if history.walletAgeDays == 0:
        parts.append((W_AGE, 0.5, False))
    else:
        parts.append((W_AGE, _clamp(history.walletAgeDays / 180.0), True))

    avail_weight = sum(w for w, _, ok in parts if ok)
    if avail_weight == 0:
        weighted = 0.5      # hoàn toàn chưa có dữ liệu -> trung tính
    else:
        weighted = sum(w * v for w, v, ok in parts if ok) / avail_weight

    raw = BASE_SCORE + (weighted - 0.5) * 2 * 500

    # ── Cáo: trừ thẳng, không để công thức pha loãng ───────────────
    if history.defaults > 0:
        penalty = min(450, 150 * history.defaults)
        raw -= penalty
        reasons.append(f"trừ {penalty} điểm do cáo")

    # ── Edu-KYC: cộng nhẹ, không phải cửa sau ──────────────────────
    if history.hasEduKyc:
        raw += 30
        reasons.append("xác thực Edu-KYC (+30)")

    s = int(_clamp(raw, 0, MAX_SCORE))

    # ── Trần góp đề xuất ───────────────────────────────────────────
    # KHÔNG phải chặn cứng: contract không cưỡng chế con số này. Đây là
    # gợi ý để chủ hụi chọn mức góp phù hợp với người chơi.
    if s >= 800:
        band, mult = "A", 10
    elif s >= 700:
        band, mult = "B", 5
    elif s >= 600:
        band, mult = "C", 2
    elif s >= 450:
        band, mult = "D", 1
    else:
        band, mult = "E", 0.5

    return ScoreResult(
        score=s,
        band=band,
        maxContribution=int(base_unit * mult),
        reasons=reasons,
        components={
            "weighted": round(weighted, 4),
            "availableWeight": round(avail_weight, 3),
            **{name: round(v, 3) for name, (_, v, ok) in zip(
                ["repayment", "completion", "experience", "bidBehaviour", "age"],
                parts)},
            "dataAvailable": [ok for _, _, ok in parts].count(True),
        },
    )


def history_from_events(address: str,
                        paid_events: list,
                        payout_events: list,
                        default_events: list,
                        bid_events: list,
                        circles_done: int = 0,
                        wallet_age_days: int = 0,
                        has_edu_kyc: bool = False) -> History:
    """
    Dựng History từ log sự kiện của contract.

    `paid_events`   : list dict {member, round, due, fee}
    `payout_events` : list dict {receiver, round, pot}
    `default_events`: list dict {member, round, covered, short}
    `bid_events`    : list dict {member, round, bid}
    """
    mine_paid = [e for e in paid_events if e["member"].lower() == address.lower()]
    mine_defaults = [e for e in default_events
                     if e["member"].lower() == address.lower()]
    mine_bids = [e for e in bid_events if e["member"].lower() == address.lower()]

    late = sum(1 for e in mine_paid if e.get("fee", 0) > 0)
    on_time = len(mine_paid) - late

    return History(
        address=address,
        roundsJoined=len(mine_paid) + len(mine_defaults),
        paidOnTime=on_time,
        paidLate=late,
        defaults=len(mine_defaults),
        bidsWon=len(mine_bids),
        avgBidRatio=0.0,
        circlesDone=circles_done,
        walletAgeDays=wallet_age_days,
        hasEduKyc=has_edu_kyc,
    )


if __name__ == "__main__":
    # Ví mới tinh
    h = History(address="0xnew")
    r = score(h)
    print(f"Ví mới        : {r.score} ({r.band}) trần góp {r.maxContribution:,}")

    # Người chơi tốt
    h2 = History(address="0xgood", roundsJoined=30, paidOnTime=30, paidLate=0,
                 defaults=0, bidsWon=2, avgBidRatio=0.1, circlesDone=3,
                 walletAgeDays=200, hasEduKyc=True)
    r2 = score(h2)
    print(f"Người chơi tốt: {r2.score} ({r2.band}) trần góp {r2.maxContribution:,}")

    # Người có lịch sử xấu
    h3 = History(address="0xbad", roundsJoined=15, paidOnTime=8, paidLate=5,
                 defaults=2, bidsWon=5, avgBidRatio=0.95, circlesDone=0,
                 walletAgeDays=30)
    r3 = score(h3)
    print(f"Lịch sử xấu  : {r3.score} ({r3.band}) trần góp {r3.maxContribution:,}")
