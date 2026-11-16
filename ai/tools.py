"""
Bộ công cụ cho AI agent.

NGUYÊN TẮC: mọi con số agent nói ra đều phải đi qua module này.
Model chỉ chọn gọi tool nào và diễn đạt kết quả; nó không được tự tính.
Nếu model bịa một con số, guardrail trong agent.py sẽ phát hiện.

Tất cả hàm ở đây là deterministic và KHÔNG cần mạng (trừ `defi_pools`),
nên test được offline.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from typing import Optional

from sim.rosca_model import max_bid as _max_bid, bid_to_apr, YEAR, BPS, MAX_APR_BPS
from ai.credit_score import History, score as _score

DEFILLAMA_POOLS = "https://yields.llama.fi/pools"


# ══════════════════════════════════════════════════════════════════
# 1. Điểm tín dụng — giải thích chi tiết
# ══════════════════════════════════════════════════════════════════

def explain_credit_score(history: History) -> dict:
    """
    Trả về điểm + phân rã từng thành phần để agent giải thích.
    Không dùng LLM: gọi thẳng công thức trong ai/credit_score.py.
    """
    r = _score(history)
    comp = r.components
    breakdown = []

    labels = {
        "repayment":    ("Trả đúng hạn",    45),
        "completion":   ("Hoàn thành dây",  20),
        "experience":   ("Kinh nghiệm",     15),
        "bidBehaviour": ("Hành vi đấu giá", 10),
        "age":          ("Tuổi ví",         10),
    }
    for key, (label, weight) in labels.items():
        val = comp.get(key)
        if val is None:
            continue
        breakdown.append({
            "thanhPhan": label,
            "trongSo": f"{weight}%",
            "diemChuanHoa": round(val, 3),
            "dienGiai": _band_text(val),
        })

    return {
        "diem": r.score,
        "hangMuc": r.band,
        "tranGopDeXuat": r.maxContribution,
        "lyDo": r.reasons,
        "phanRa": breakdown,
        "soThanhPhanCoDuLieu": comp.get("dataAvailable", 0),
        "goiYSua": _advice_for_band(r.band, comp),
    }


def _band_text(v: float) -> str:
    if v >= 0.85:
        return "tốt"
    if v >= 0.6:
        return "khá"
    if v >= 0.35:
        return "yếu"
    return "kém"


def _advice_for_band(band: str, comp: dict) -> list:
    """Gợi ý cải thiện điểm, dựa trên thành phần yếu nhất."""
    out = []
    ranked = [
        ("repayment", "đóng đúng hạn", "mỗi kỳ trễ làm giảm điểm trả đúng hạn"),
        ("completion", "chơi hết dây", "bỏ giữa chừng bị tính là cáo"),
        ("experience", "tham gia thêm vòng", "cần khoảng 20 vòng để đạt tối đa"),
        ("bidBehaviour", "kêu giá vừa phải", "kêu sát trần bị coi là hớt váng"),
        ("age", "giữ ví hoạt động lâu hơn", "cần khoảng 180 ngày"),
    ]
    scored = [(comp.get(k, 0.5), label, hint) for k, label, hint in ranked]
    scored.sort()
    for val, label, hint in scored[:2]:
        if val < 0.9:
            out.append(f"Cải thiện '{label}': {hint} (hiện {_band_text(val)})")
    return out


# ══════════════════════════════════════════════════════════════════
# 2. Trạng thái dây hụi — chiến lược chơi
# ══════════════════════════════════════════════════════════════════

def circle_status(
    member_count: int,
    contribution: int,
    period: int,
    current_round: int,
    mode: str,
    received: list,
    paid_this_round: list,
    penalty_pool: int = 0,
) -> dict:
    """
    Tóm tắt trạng thái dây hụi để agent tư vấn chiến lược.

    received          : list địa chỉ đã nhận pot (theo thứ tự)
    paid_this_round   : list địa chỉ đã đóng kỳ này
    """
    n = member_count
    rounds_left = n - current_round
    not_yet_received = n - len(received)
    # Vị trí trung bình trong hàng chờ nhận
    avg_wait = (not_yet_received + 1) / 2.0 if not_yet_received else 0.0

    return {
        "soNguoi": n,
        "gopMoiKy": contribution,
        "kyHienTai": current_round + 1,
        "tongSoKy": n,
        "soKyConLai": rounds_left,
        "cheDo": mode,
        "daNhanPot": len(received),
        "chuaNhanPot": not_yet_received,
        "soNguoiDaDongKyNay": len(paid_this_round),
        "soNguoiChuaDong": n - len(paid_this_round),
        "quyPhat": penalty_pool,
        # Trừ 1 cho người nhận pot kỳ này (không phải đóng).
    "uocTinhChoTrungBinh": round(avg_wait, 1),
        "nhanXet": _strategy_notes(n, current_round, received, not_yet_received),
    }


def _strategy_notes(n, cur, received, not_yet) -> list:
    notes = []
    if cur == 0:
        notes.append("Vòng đầu: chưa ai nhận, mọi người ngang nhau.")
    if not_yet == 0:
        notes.append("Tất cả đã nhận pot — chỉ còn nghĩa vụ đóng hụi chết.")
    elif not_yet == 1:
        notes.append("Chỉ còn 1 người chưa nhận ở vòng cuối cùng.")
    frac = len(received) / n if n else 0
    if frac >= 0.7:
        notes.append(
            f"Đã {frac:.0%} thành viên nhận — rủi ro bùng hụi cao nhất ở giai "
            "đoạn này vì người đã nhận không còn gì để mất ngoài ký quỹ."
        )
    elif frac <= 0.3 and cur > 0:
        notes.append("Còn đa số chưa nhận — nhóm vẫn còn động lực đóng đều.")
    return notes


# ══════════════════════════════════════════════════════════════════
# 3. Mô phỏng kêu giá — gợi ý mức bid
# ══════════════════════════════════════════════════════════════════

def simulate_bid(
    contribution: int,
    period: int,
    bid: int,
    receive_round: int,
    member_count: int,
    prior_bid: int | None = None,
) -> dict:
    """
    Nếu kêu giá `bid` và nhận pot ở vòng `receive_round`, lãi/lỗ ròng là bao nhiêu?

    `receive_round` 1-based, khớp với số kỳ người dùng thấy trên UI.
    `prior_bid`     giá kêu giả định ở các vòng TRƯỚC khi mình nhận.
                    Mặc định = `bid` (giả định các vòng tương tự nhau).
                    Đây là giả định, không phải sự thật on-chain — các vòng
                    khác có thể có mức giá khác. Agent phải nói rõ điều này.

    Công thức (khớp sim/rosca_model.py):
      Nhận pot = (n-1)*(A-d) + (số người đã nhận trước)*d
      Tổng đóng:
        · các vòng TRƯỚC khi nhận: đóng (A - prior_bid) mỗi vòng
        · vòng mình nhận: không đóng
        · các vòng SAU khi nhận: đóng đủ A (hụi chết)
      net = pot - tổng đóng

    Kiểm chứng zero-sum: với n thành viên nhận lần lượt các vòng 1..n và
    cùng mức giá d, net(r) = d*(2r - n - 1), tổng theo r = 0.
    """
    n = member_count
    if not (1 <= receive_round <= n):
        return {"loi": f"vòng nhận phải trong 1..{n}"}
    if bid < 0:
        return {"loi": "giá kêu không âm"}
    cap = _max_bid(contribution, period)
    if bid > cap:
        return {
            "loi": f"vượt trần 20%/năm (tối đa {cap:,} mỗi kỳ)",
            "tranToiDa": cap,
        }

    d_prior = bid if prior_bid is None else prior_bid
    before = receive_round - 1          # số người đã nhận trước mình

    pot = (n - 1) * (contribution - bid) + before * bid

    paid_before = before * (contribution - d_prior)
    paid_after = (n - receive_round) * contribution
    total_paid = paid_before + paid_after

    net = pot - total_paid
    apr = bid_to_apr(contribution, period, bid) if bid else 0.0

    return {
        "vongNhan": receive_round,
        "giaKeu": bid,
        "apr": round(apr, 2),
        "tranToiDa": cap,
        "conDuoiTran": cap - bid,
        "potNhanDuoc": pot,
        "dongTruocKhiNhan": paid_before,
        "dongSauKhiNhan": paid_after,
        "tongPhaiDong": total_paid,
        "laiLoRong": net,
        "ketLuan": "lời" if net > 0 else ("lỗ" if net < 0 else "hoà"),
        "giaDinh": (
            f"Giả định các vòng trước cũng kêu giá {d_prior:,}/kỳ. "
            "Giá thực tế từng vòng có thể khác."
        ),
        "dienGiai": (
            f"Nhận {pot:,} ở vòng {receive_round}. Đóng "
            f"{before} kỳ trước × {contribution - d_prior:,} = {paid_before:,}, "
            f"sau đó {n - receive_round} kỳ × {contribution:,} = {paid_after:,}. "
            f"Ròng {'+' if net >= 0 else ''}{net:,}."
        ),
    }


def bid_advice(contribution: int, period: int, member_count: int) -> dict:
    """
    Gợi ý dải giá kêu hợp lý, dựa trên chi phí thực của việc nhận sớm.
    Trả về 3 mức: thấp / vừa / cao, kèm hệ quả.
    """
    cap = _max_bid(contribution, period)
    out = []
    for name, frac, rnd in [("an toàn", 0.25, member_count),
                            ("vừa phải", 0.5, max(1, member_count // 2)),
                            ("cần tiền gấp", 1.0, 1)]:
        b = int(cap * frac)
        sim = simulate_bid(contribution, period, b, rnd, member_count)
        out.append({
            "muc": name,
            "giaKeu": b,
            "apr": sim.get("apr"),
            "vongNhanDuKien": rnd,
            "laiLoRong": sim.get("laiLoRong"),
            "dienGiai": sim.get("dienGiai"),
        })
    return {
        "tranToiDa": cap,
        "aprTran": round(MAX_APR_BPS / 100, 1),
        "cacMuc": out,
        "luuY": (
            "Kêu giá cao hơn = nhận sớm hơn nhưng lỗ nhiều hơn. "
            "Trần 20%/năm là giới hạn pháp lý (Điều 468 BLDS 2015), "
            "contract sẽ revert nếu vượt."
        ),
    }


# ══════════════════════════════════════════════════════════════════
# 4. Yield — DefiLlama
# ══════════════════════════════════════════════════════════════════

def defi_pools(top: int = 5, min_tvl: float = 1_000_000) -> dict:
    """
    Lấy pool lending có APY cao trên Avalanche từ DefiLlama.
    Cần mạng. Nếu lỗi → trả về `loi` và danh sách rỗng (agent phải nói
    thật là không lấy được dữ liệu, không được bịa APY).
    """
    try:
        req = urllib.request.Request(
            DEFILLAMA_POOLS,
            headers={"User-Agent": "hui-onchain/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"loi": f"không gọi được DefiLlama ({e.__class__.__name__})",
                "pools": []}

    rows = []
    for p in data.get("data", []):
        if p.get("chain") != "Avalanche":
            continue
        if (p.get("tvlUsd") or 0) < min_tvl:
            continue
        if p.get("exposure") not in ("single", None):
            continue
        apy = p.get("apy")
        if apy is None or apy <= 0 or apy > 60:   # lọc APY bất thường
            continue
        rows.append({
            "pool": p.get("symbol"),
            "project": p.get("project"),
            "apy": round(apy, 2),
            "tvlUsd": int(p.get("tvlUsd") or 0),
            "ilRisk": p.get("ilRisk"),
            "stablecoin": p.get("stablecoin"),
        })

    rows.sort(key=lambda x: x["apy"], reverse=True)
    return {
        "pools": rows[:top],
        "tongSoPoolAvalanche": len(rows),
        "luuY": (
            "APY cao hơn nhiều so với phần còn lại thường đi kèm rủi ro "
            "cao hơn (IL, thanh khoản mỏng, token thưởng có thể mất giá). "
            "Dự án chỉ gợi ý, không tự chuyển tiền — người dùng bấm nút."
        ),
    }
