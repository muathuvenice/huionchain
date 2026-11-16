"""
Test cho AI agent + tools. Chạy offline, không cần GEMINI_API_KEY.

    python3 -m unittest ai.test_agent -v

Trọng tâm:
  1. Toán của tool phải đúng (zero-sum, trần 20%, pot).
  2. Guardrail phải BẮT ĐƯỢC số bịa.
  3. Không có LLM thì vẫn trả lời hữu ích, không crash.
"""
import unittest
from unittest.mock import patch

from ai import agent, tools, llm
from ai.credit_score import History
from sim.rosca_model import max_bid, YEAR


A = 1_000_000
P = 30 * 86_400
N = 10


class TestSimulateBid(unittest.TestCase):
    """Toán mô phỏng kêu giá — phần dễ sai nhất."""

    def test_zero_sum_across_all_rounds(self):
        """Tổng lãi/lỗ của n người nhận lần lượt các vòng phải bằng 0."""
        d = max_bid(A, P)
        total = sum(
            tools.simulate_bid(A, P, d, r, N)["laiLoRong"]
            for r in range(1, N + 1)
        )
        self.assertEqual(total, 0, f"tổng net = {total:,}, phải bằng 0")

    def test_matches_closed_form(self):
        """net(r) = d·(2r − n − 1) khi các vòng cùng mức giá."""
        d = max_bid(A, P)
        for r in range(1, N + 1):
            got = tools.simulate_bid(A, P, d, r, N)["laiLoRong"]
            want = d * (2 * r - N - 1)
            self.assertEqual(got, want, f"vòng {r}: {got:,} != {want:,}")

    def test_early_receiver_loses(self):
        d = max_bid(A, P)
        self.assertLess(tools.simulate_bid(A, P, d, 1, N)["laiLoRong"], 0)

    def test_late_receiver_gains(self):
        d = max_bid(A, P)
        self.assertGreater(tools.simulate_bid(A, P, d, N, N)["laiLoRong"], 0)

    def test_zero_bid_is_neutral(self):
        """Không kêu giá (d=0) thì mọi người hoà vốn."""
        for r in range(1, N + 1):
            self.assertEqual(
                tools.simulate_bid(A, P, 0, r, N)["laiLoRong"], 0)

    def test_bid_above_cap_rejected(self):
        cap = max_bid(A, P)
        res = tools.simulate_bid(A, P, cap + 1, 1, N)
        self.assertIn("loi", res)
        self.assertIn("20%", res["loi"])

    def test_bid_at_cap_allowed(self):
        cap = max_bid(A, P)
        self.assertNotIn("loi", tools.simulate_bid(A, P, cap, 1, N))

    def test_invalid_round_rejected(self):
        self.assertIn("loi", tools.simulate_bid(A, P, 0, 0, N))
        self.assertIn("loi", tools.simulate_bid(A, P, 0, N + 1, N))

    def test_pot_never_exceeds_physical_max(self):
        """pot không bao giờ vượt (n-1)·A — nếu vượt là contract tạo ra tiền."""
        cap = max_bid(A, P)
        for bid in (0, cap // 2, cap):
            for r in range(1, N + 1):
                pot = tools.simulate_bid(A, P, bid, r, N)["potNhanDuoc"]
                self.assertLessEqual(pot, (N - 1) * A, f"bid={bid} r={r}")


class TestBidAdvice(unittest.TestCase):
    def test_three_tiers_returned(self):
        res = tools.bid_advice(A, P, N)
        self.assertEqual(len(res["cacMuc"]), 3)

    def test_all_tiers_within_cap(self):
        res = tools.bid_advice(A, P, N)
        cap = max_bid(A, P)
        for m in res["cacMuc"]:
            self.assertLessEqual(m["giaKeu"], cap)
            self.assertLessEqual(m["apr"], 20.0)

    def test_risky_tier_costs_most(self):
        res = tools.bid_advice(A, P, N)
        safe = res["cacMuc"][0]["laiLoRong"]
        risky = res["cacMuc"][2]["laiLoRong"]
        self.assertGreater(safe, risky)


class TestCircleStatus(unittest.TestCase):
    def test_member_counts_add_up(self):
        res = tools.circle_status(
            N, A, P, 3, "Bidding",
            ["0xa", "0xb", "0xc"], ["0xa", "0xb", "0xc", "0xd"], 250_000)
        self.assertEqual(
            res["soNguoiDaDongKyNay"] + res["soNguoiChuaDong"], N)

    def test_flags_high_bust_risk(self):
        """Đã 70%+ nhận pot → phải cảnh báo rủi ro bùng."""
        res = tools.circle_status(
            N, A, P, 7, "Bidding", [f"0x{i}" for i in range(8)], [], 0)
        joined = " ".join(res["nhanXet"])
        self.assertIn("bùng", joined)

    def test_no_warning_early(self):
        res = tools.circle_status(N, A, P, 1, "Bidding", ["0xa"], [], 0)
        joined = " ".join(res["nhanXet"])
        self.assertNotIn("rủi ro bùng hụi cao nhất", joined)


class TestCreditExplain(unittest.TestCase):
    def test_fresh_wallet_neutral(self):
        res = tools.explain_credit_score(History("0xnew"))
        self.assertEqual(res["diem"], 500)

    def test_breakdown_has_five_parts(self):
        res = tools.explain_credit_score(
            History("0xa", roundsJoined=20, paidOnTime=20))
        self.assertEqual(len(res["phanRa"]), 5)

    def test_weights_are_stated(self):
        res = tools.explain_credit_score(History("0xa", paidOnTime=5,
                                                 roundsJoined=5))
        weights = [p["trongSo"] for p in res["phanRa"]]
        self.assertEqual(weights, ["45%", "20%", "15%", "10%", "10%"])

    def test_gives_advice_on_weakest(self):
        res = tools.explain_credit_score(History("0xa", paidOnTime=5,
                                                 roundsJoined=5))
        self.assertTrue(res["goiYSua"])


class TestGuardrail(unittest.TestCase):
    """Guardrail phải bắt được số bịa — đây là điểm quan trọng nhất."""

    TOOL_RESULTS = [
        {"tool": "simulate_bid", "ketQua": tools.simulate_bid(
            A, P, max_bid(A, P), 1, N)},
    ]

    def test_catches_fabricated_number(self):
        bogus = "Bạn sẽ lỗ khoảng 7.777.777 đồng nếu kêu giá này."
        ok, bad = agent._numbers_are_grounded(bogus, self.TOOL_RESULTS)
        self.assertFalse(ok, "phải bắt được số bịa")
        self.assertIn(7777777.0, bad)

    def test_accepts_real_number(self):
        real = "Bạn sẽ lỗ 147.942 đồng nếu nhận ở vòng 1."
        ok, bad = agent._numbers_are_grounded(real, self.TOOL_RESULTS)
        self.assertTrue(ok, f"phải chấp nhận số thật, nhưng báo {bad}")

    def test_accepts_small_numbers(self):
        text = "Có 10 người, vòng 1, trần 20%/năm."
        ok, _ = agent._numbers_are_grounded(text, self.TOOL_RESULTS)
        self.assertTrue(ok)

    def test_accepts_rounded_number(self):
        """Model làm tròn 147.942 → 148.000 vẫn phải chấp nhận."""
        text = "Bạn lỗ khoảng 148.000 đồng."
        ok, _ = agent._numbers_are_grounded(text, self.TOOL_RESULTS)
        self.assertTrue(ok)

    def test_rejects_number_with_no_tools(self):
        ok, bad = agent._numbers_are_grounded(
            "Bạn sẽ nhận được 9.999.999 đồng.", [])
        self.assertFalse(ok)


class TestAgentWithoutLLM(unittest.TestCase):
    """Không có API key → phải trả lời hữu ích bằng tool, không crash."""

    def setUp(self):
        self.ctx = agent.AgentContext(
            history=History("0xa", roundsJoined=10, paidOnTime=9, paidLate=1),
            member_count=N, contribution=A, period=P,
            current_round=2, mode="Bidding",
            received=["0xa", "0xb"], paid_this_round=["0xc"],
            penalty_pool=100_000,
        )

    @patch.dict("os.environ", {}, clear=True)
    def test_no_key_still_answers(self):
        res = agent.ask("Điểm uy tín của tôi thế nào?", self.ctx)
        self.assertTrue(res["fallback"])
        self.assertIn("Điểm", res["answer"])

    @patch.dict("os.environ", {}, clear=True)
    def test_no_key_routes_by_keyword(self):
        res = agent.ask("Nên kêu giá bao nhiêu?", self.ctx)
        self.assertIn("kêu", res["answer"].lower())

    @patch.dict("os.environ", {}, clear=True)
    def test_no_key_status_question(self):
        res = agent.ask("Tình hình dây hụi thế nào?", self.ctx)
        self.assertIn("người", res["answer"])


class TestAgentWithMockedLLM(unittest.TestCase):
    """Mô phỏng model gọi tool rồi trả lời — kiểm tra vòng lặp."""

    def setUp(self):
        self.ctx = agent.AgentContext(
            history=History("0xa", roundsJoined=20, paidOnTime=20),
            member_count=N, contribution=A, period=P,
            current_round=1, mode="Bidding", received=[], paid_this_round=[],
        )

    def test_loop_executes_tool_then_answers(self):
        calls = []

        def fake_chat(sysp, userp, tools=None, history=None):
            calls.append(userp)
            if len(calls) == 1:
                return {"ok": True, "text": "", "tool_calls": [
                    {"name": "circle_status", "args": {}}], "raw": {}}
            return {"ok": True, "text": "Dây có 10 người, đang kỳ 1.",
                    "tool_calls": [], "raw": {}}

        with patch.object(llm, "chat", side_effect=fake_chat):
            res = agent.ask("Tình hình dây?", self.ctx)

        self.assertEqual(res["toolCalls"], ["circle_status"])
        self.assertTrue(res["grounded"])
        self.assertFalse(res["fallback"])

    def test_fabricated_answer_is_replaced(self):
        """Model trả lời bịa số → phải bị thay bằng bản deterministic."""
        calls = []

        def fake_chat(sysp, userp, tools=None, history=None):
            calls.append(userp)
            if len(calls) == 1:
                return {"ok": True, "text": "", "tool_calls": [
                    {"name": "circle_status", "args": {}}], "raw": {}}
            return {"ok": True,
                    "text": "Bạn sẽ nhận được 55.555.555 đồng chắc chắn.",
                    "tool_calls": [], "raw": {}}

        with patch.object(llm, "chat", side_effect=fake_chat):
            res = agent.ask("Tôi được bao nhiêu?", self.ctx)

        self.assertFalse(res["grounded"])
        self.assertTrue(res["fallback"])
        self.assertNotIn("55.555.555", res["answer"])
        self.assertEqual(res["error"], "ungrounded_numbers_replaced")

    def test_unknown_tool_does_not_crash(self):
        calls = []

        def fake_chat(sysp, userp, tools=None, history=None):
            calls.append(userp)
            if len(calls) == 1:
                return {"ok": True, "text": "", "tool_calls": [
                    {"name": "nonexistent_tool", "args": {}}], "raw": {}}
            return {"ok": True, "text": "Xong.", "tool_calls": [], "raw": {}}

        with patch.object(llm, "chat", side_effect=fake_chat):
            res = agent.ask("test", self.ctx)
        self.assertIn("nonexistent_tool", res["toolCalls"])

    def test_tool_exception_is_contained(self):
        """Tool ném exception không được làm sập agent."""
        ctx = agent.AgentContext(member_count=0)   # chưa kết nối dây
        res = agent.run_tool("simulate_bid", {"bid": 1, "receive_round": 1},
                             ctx)
        self.assertIn("loi", res)


class TestToolCatalogue(unittest.TestCase):
    def test_all_declared_tools_are_runnable(self):
        ctx = agent.AgentContext(
            history=History("0xa"), member_count=N,
            contribution=A, period=P, current_round=0,
        )
        for decl in agent.TOOL_DECLS:
            res = agent.run_tool(decl["name"], {"bid": 0, "receive_round": 1},
                                 ctx)
            self.assertIsInstance(res, dict)
            self.assertNotIn("không có tool", str(res.get("loi", "")))

    def test_declarations_have_required_fields(self):
        for decl in agent.TOOL_DECLS:
            self.assertIn("name", decl)
            self.assertIn("description", decl)
            self.assertIn("parameters", decl)


class TestLLMParsing(unittest.TestCase):
    """Parse response Gemini — không cần gọi mạng."""

    def test_extracts_text(self):
        resp = {"candidates": [{"content": {"parts": [{"text": "Xin chào"}]}}]}
        out = llm._parse_gemini_response(resp)
        self.assertEqual(out["text"], "Xin chào")
        self.assertTrue(out["ok"])

    def test_extracts_function_call(self):
        resp = {"candidates": [{"content": {"parts": [
            {"functionCall": {"name": "circle_status", "args": {}}}]}}]}
        out = llm._parse_gemini_response(resp)
        self.assertEqual(out["tool_calls"][0]["name"], "circle_status")

    def test_empty_candidates(self):
        out = llm._parse_gemini_response({"candidates": []})
        self.assertFalse(out["ok"])

    def test_text_and_call_together(self):
        resp = {"candidates": [{"content": {"parts": [
            {"text": "Để tôi kiểm tra."},
            {"functionCall": {"name": "bid_advice", "args": {}}}]}}]}
        out = llm._parse_gemini_response(resp)
        self.assertEqual(out["text"], "Để tôi kiểm tra.")
        self.assertEqual(len(out["tool_calls"]), 1)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_history_maps_assistant_role_to_model(self):
        captured = {}

        def fake_post(payload, api_key):
            captured["payload"] = payload
            return {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}

        with patch.object(llm, "_post", side_effect=fake_post):
            res = llm.chat(
                "sys",
                "Câu hỏi mới",
                history=[
                    {"role": "user", "content": "Chào"},
                    {"role": "assistant", "content": "Xin chào"},
                ],
            )
        self.assertTrue(res["ok"])
        roles = [c["role"] for c in captured["payload"]["contents"]]
        self.assertEqual(roles, ["user", "model", "user"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
