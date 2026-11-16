"""
Test phần logic không cần Streamlit, không cần mạng.
Chạy: python3 -m unittest app.test_logic -v
"""
import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.credit_score import History, score, history_from_events, BASE_SCORE
from app.chain import CircleView, MemberView, fmt_usdc, MODE_NAMES, PHASE_NAMES


class TestCreditScore(unittest.TestCase):
    def test_fresh_wallet_is_neutral(self):
        """Ví mới phải ra đúng điểm trung tính, không bị phạt vì thiếu lịch sử."""
        r = score(History(address="0xnew"))
        self.assertEqual(r.score, BASE_SCORE,
                         "ví mới phải trung tính, tránh cold start")

    def test_good_player_scores_high(self):
        h = History(address="0xg", roundsJoined=30, paidOnTime=30,
                    paidLate=0, defaults=0, bidsWon=2, avgBidRatio=0.1,
                    circlesDone=3, walletAgeDays=200, hasEduKyc=True)
        r = score(h)
        self.assertGreaterEqual(r.score, 900)
        self.assertEqual(r.band, "A")

    def test_default_destroys_score(self):
        h = History(address="0xb", roundsJoined=20, paidOnTime=18,
                    paidLate=2, defaults=3, bidsWon=4, avgBidRatio=0.9,
                    circlesDone=0, walletAgeDays=100)
        r = score(h)
        self.assertLess(r.score, 300)
        self.assertIn(r.band, ("D", "E"))

    def test_one_default_costs_heavily(self):
        """Một lần cáo phải nói nhiều hơn nhiều kỳ trả đúng."""
        good = History(address="0xa", roundsJoined=20, paidOnTime=20,
                       defaults=0, circlesDone=2, walletAgeDays=150)
        with_default = History(address="0xa", roundsJoined=20, paidOnTime=19,
                               paidLate=1, defaults=1, circlesDone=2,
                               walletAgeDays=150)
        drop = score(good).score - score(with_default).score
        self.assertGreater(drop, 200, f"chỉ giảm {drop} điểm là quá nhẹ")

    def test_score_bounded(self):
        extreme = History(address="0xz", roundsJoined=999, paidOnTime=999,
                          defaults=0, circlesDone=99, walletAgeDays=9999)
        self.assertLessEqual(score(extreme).score, 1000)
        worst = History(address="0xz", roundsJoined=99, paidLate=99,
                        defaults=99, avgBidRatio=1.0, bidsWon=99)
        self.assertGreaterEqual(score(worst).score, 0)

    def test_late_reduces_but_less_than_default(self):
        late = History(address="0xl", roundsJoined=20, paidOnTime=15,
                       paidLate=5, defaults=0, circlesDone=2)
        defaulted = History(address="0xd", roundsJoined=20, paidOnTime=15,
                            paidLate=5, defaults=1, circlesDone=2)
        self.assertGreater(score(late).score, score(defaulted).score)

    def test_max_contribution_monotonic(self):
        """Điểm cao hơn không bao giờ được đề xuất trần góp thấp hơn."""
        prev = 0
        for s in range(0, 1001, 50):
            # dựng History để rơi vào khoảng điểm mong muốn là phức tạp;
            # thay vào đó kiểm tra trực tiếp bảng band.
            pass
        # kiểm tra bảng band trực tiếp
        from ai.credit_score import score as sc
        rows = []
        for paid in range(0, 21):
            h = History(address="0x", roundsJoined=paid, paidOnTime=paid,
                        defaults=0, circlesDone=min(3, paid // 7),
                        walletAgeDays=min(180, paid * 10))
            rows.append((sc(h).score, sc(h).maxContribution))
        rows.sort()
        caps = [c for _, c in rows]
        self.assertEqual(caps, sorted(caps), "trần góp phải đơn điệu theo điểm")

    def test_reasons_are_present(self):
        r = score(History(address="0x", roundsJoined=10, paidOnTime=8,
                          paidLate=2, defaults=1))
        self.assertTrue(r.reasons, "phải có lý do để hiển thị cho người dùng")
        self.assertTrue(any("cáo" in x for x in r.reasons))


class TestHistoryFromEvents(unittest.TestCase):
    def test_builds_correctly(self):
        paid = [{"member": "0xA", "round": 0, "due": 100, "fee": 0},
                {"member": "0xA", "round": 1, "due": 100, "fee": 2}]
        default = [{"member": "0xB", "round": 0, "covered": 50, "short": 50}]
        h = history_from_events("0xa", paid, [], default, [])
        self.assertEqual(h.paidOnTime, 1)
        self.assertEqual(h.paidLate, 1)
        self.assertEqual(h.defaults, 0)
        self.assertEqual(h.roundsJoined, 2)

    def test_case_insensitive_address_match(self):
        paid = [{"member": "0xABCDEF", "round": 0, "due": 1, "fee": 0}]
        h = history_from_events("0xabcdef", paid, [], [], [])
        self.assertEqual(h.paidOnTime, 1)


class TestFormatting(unittest.TestCase):
    def test_fmt_usdc(self):
        self.assertEqual(fmt_usdc(1_000_000), "1.00")
        self.assertEqual(fmt_usdc(1_500_000), "1.50")
        self.assertEqual(fmt_usdc(0), "0.00")

    def test_mode_and_phase_names(self):
        self.assertEqual(MODE_NAMES[0], "Cố định")
        self.assertEqual(MODE_NAMES[1], "Đấu giá")
        self.assertEqual(PHASE_NAMES[3], "Đã đóng")

    def test_member_net(self):
        m = MemberView(address="0x", index=0, paid_total=100,
                       received_total=250, won_round=1, deposit_left=10,
                       late_count=0, default_round=None, amount_due=0)
        self.assertEqual(m.net, 150)
        self.assertEqual(m.status, "Đã nhận (vòng 1)")


class TestAgentBridge(unittest.TestCase):
    def test_empty_context_when_disconnected(self):
        from app.agent_bridge import build_agent_context
        ctx = build_agent_context(None, "")
        self.assertEqual(ctx.member_count, 0)
        self.assertIsNone(ctx.history)

    def test_builds_context_with_period_and_history(self):
        from app.agent_bridge import build_agent_context_from_data
        from ai import agent
        c = CircleView(
            address="0xcircle",
            mode=1,
            phase=2,
            member_count=4,
            contribution=10_000_000,
            deposit=10_000_000,
            current_round=1,
            max_bid=50_000,
            total_pool=40_000_000,
            deposits_held=40_000_000,
            penalty_pool=200_000,
            shortfall=0,
            period=300,
        )
        events = [
            {"type": "payout", "receiver": "0xA", "round": 0, "pot": 30_000_000},
            {"type": "pay", "member": "0xB", "round": 0, "due": 10_000_000, "fee": 0},
            {"type": "pay", "member": "0xB", "round": 1, "due": 10_000_000, "fee": 200_000},
            {"type": "reveal", "member": "0xB", "round": 1, "bid": 25_000},
        ]
        ctx = build_agent_context_from_data(c, events, me="0xb")
        self.assertEqual(ctx.period, 300)
        self.assertEqual(ctx.mode, "Đấu giá")
        self.assertEqual(ctx.received, ["0xA"])
        self.assertEqual(ctx.paid_this_round, ["0xB"])
        self.assertEqual(ctx.penalty_pool, 200_000)
        self.assertIsNotNone(ctx.history)
        self.assertEqual(ctx.history.paidOnTime, 1)
        self.assertEqual(ctx.history.paidLate, 1)
        self.assertAlmostEqual(ctx.history.avgBidRatio, 0.5)

        res = agent.ask("Nên kêu giá bao nhiêu?", ctx)
        self.assertTrue(res["answer"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
