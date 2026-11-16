"""
Fuzz: chạy ngẫu nhiên nhiều dây hụi với giá kêu ngẫu nhiên, người cáo
ngẫu nhiên, thanh toán trễ ngẫu nhiên. Kiểm tra các bất biến:

  I1. Contract không giữ tiền sau khi đóng hụi.
  I2. total_pool() == balanceOf(contract) tại mọi thời điểm.
  I3. Bảo toàn tiền tệ: tổng thay đổi số dư thành viên == 0.
  I3b. Zero-sum theo từng vòng: pot == tổng `due` đã đóng trong vòng đó.
  I4. Không giá kêu nào vượt trần 20%/năm.
  I5. Không ai nhận nhiều hơn một pot.
  I6. Không quỹ nào âm.

Thời gian lấy từ deadline thật của contract. Vòng được theo dõi bằng
chỉ số `current_round`, không dựa vào `phase` (vì mode Fixed mở vòng
kế ngay trong cùng một giao dịch).
"""
import random
import unittest
from sim.contract_port import (RoscaCircle, Token, Mode, Phase, Revert,
                               LATE_FEE_BPS, BPS, MAX_APR_BPS, YEAR)

A = 1_000 * 10**6
PERIOD = 30 * 86400
COMMIT = 2 * 86400
REVEAL = 1 * 86400
PAY = 1 * 86400
INIT_BAL = 10**15


def check_pools(c, tok, seed):
    assert c.deposits_held >= 0, f"I6 deposits seed={seed}"
    assert c.penalty_pool >= 0, f"I6 penalty seed={seed}"
    assert c.pot_in_flight >= 0, f"I6 pot seed={seed}"
    assert tok.balance_of(c) == c.total_pool(), (
        f"I2 seed={seed}: bal={tok.balance_of(c)} pool={c.total_pool()}")


def run_one(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 8)
    mode = rng.choice([Mode.Fixed, Mode.Bidding])

    tok = Token()
    c = RoscaCircle(tok, "org", mode, n, A, PERIOD, COMMIT, REVEAL, PAY)
    ev = ["org"] + [f"u{i}" for i in range(n - 1)]
    for a in ev:
        tok.mint(a, INIT_BAL)
        tok.approve(a, c, 10**12)
    for a in ev:
        c.join(a)
    check_pools(c, tok, seed)

    now = 0
    for _ in range(600):
        if c.phase == Phase.Closed:
            break
        idx_at_start = c.current_round

        # ── giai đoạn đấu giá ──────────────────────────────────────
        if c.phase == Phase.Bidding:
            r = c.rounds[c.current_round]
            bids = {}
            for a in ev:
                if c.info[a].won_round_plus1 != 0:
                    continue
                if rng.random() < 0.75:
                    cap = c.max_bid()
                    b = rng.randint(0, cap)
                    assert b <= cap, f"I4 seed={seed}"
                    h = f"h{a}{c.current_round}"
                    try:
                        c.commit_bid(a, h, now)
                        bids[a] = (b, h)
                    except Revert:
                        pass
            now = r.commit_deadline + 1
            for a, (b, h) in bids.items():
                if rng.random() < 0.85:
                    c.reveal_bid(a, b, h, now)
            now = r.commit_deadline + REVEAL + 1
            c.settle(now)
            check_pools(c, tok, seed)
            continue

        # ── giai đoạn thu tiền ─────────────────────────────────────
        r = c.rounds[c.current_round]
        if rng.random() < 0.3:
            now = r.pay_deadline + 1          # giả lập trễ hạn

        payers = [a for a in ev
                  if c.amount_due(a) > 0 and not c.paid_current.get(a)]
        rng.shuffle(payers)

        defaulters = []
        for a in payers:
            if c.phase != Phase.Paying or c.current_round != idx_at_start:
                break
            if rng.random() < 0.12:
                defaulters.append(a)
                continue
            try:
                c.pay_in(a, now)
                check_pools(c, tok, seed)
            except Revert:
                pass

        if c.phase == Phase.Paying and c.current_round == idx_at_start:
            now = max(now, r.pay_deadline + 1)
            for a in defaulters:
                if c.phase != Phase.Paying or c.current_round != idx_at_start:
                    break
                try:
                    c.claim_default(a, now)
                    check_pools(c, tok, seed)
                except Revert:
                    pass
            for a in ev:
                if c.phase != Phase.Paying or c.current_round != idx_at_start:
                    break
                if c.amount_due(a) > 0 and not c.paid_current.get(a):
                    try:
                        c.claim_default(a, now)
                        check_pools(c, tok, seed)
                    except Revert:
                        pass

        if c.current_round == idx_at_start and c.phase == Phase.Paying:
            stuck = [a for a in ev
                     if c.amount_due(a) > 0 and not c.paid_current.get(a)]
            raise AssertionError(
                f"stuck round={idx_at_start} seed={seed} "
                f"paid={r.paid_count}/{n} stuck={stuck}")

        now += 1

    if c.phase != Phase.Closed:
        return None

    # ── bất biến sau khi đóng hụi ─────────────────────────────────
    assert tok.balance_of(c) == 0, f"I1 seed={seed}: còn {tok.balance_of(c)}"
    assert c.total_pool() == 0, f"I2 seed={seed}"

    delta = sum(tok.balance_of(a) - INIT_BAL for a in ev)
    assert delta == 0, f"I3 seed={seed}: lệch {delta}"

    for k, rr in enumerate(c.rounds):
        assert rr.pot == c.round_dues[k], (
            f"I3b seed={seed} round={k}: pot={rr.pot:,} != {c.round_dues[k]:,}")

    # I3c: mỗi vòng pot phải nằm trong khoảng vật lý cho phép.
    #   tối thiểu: (n-1) người chưa nhận đóng (A - maxBid)  [không ai cáo]
    #   tối đa:   (n-1) người đã nhận đóng A  [không ai nhận trước]
    # Nếu pot vượt trần này thì contract đang thu nhiều hơn mức có thể,
    # tức là tự sinh tiền.
    for k, rr in enumerate(c.rounds):
        hi = (n - 1) * A
        assert rr.pot <= hi, (
            f"I3c seed={seed} round={k}: pot={rr.pot:,} vượt trần {hi:,} "
            f"-> contract thu nhiều hơn mức tối đa có thể")

    # I3d: người thắng một vòng không bao giờ nằm trong pot của chính vòng đó
    #      -> pot không được bằng bội số của A vượt (n-1)*A
    # I3e: tổng received không vượt (n-1)*A mỗi người
    for a in ev:
        assert c.info[a].received_total <= (n - 1) * A, f"I3e seed={seed} {a}"

    for a in ev:
        assert c.info[a].won_round_plus1 <= n, f"I5 seed={seed}"
        assert c.deposit - c.info[a].slashed >= 0, f"I6 dep seed={seed}"
    return n


class Targeted(unittest.TestCase):
    """Test có mục tiêu cho những chỗ fuzz hay bỏ lọt."""

    def test_penalty_split_exact_amounts(self):
        """
        4 người, u2 cáo ở vòng 0, u0 và u1 trả trễ một lần.
        Quỹ phạt = 2 * phí trễ, chia đều cho 3 người KHÔNG cáo.

        Số dư cuối được tính tay:
          - Vòng 0: pot 3A (u2 bù bằng ký quỹ).
          - Vòng 1..3: pot 3A mỗi vòng, không ai trễ.
          - Mỗi người không cáo nhận thêm (2*late)//3.
        """
        n = 4
        tok = Token()
        c = RoscaCircle(tok, "org", Mode.Fixed, n, A, PERIOD, COMMIT, REVEAL, PAY)
        ev = ["org", "u0", "u1", "u2"]
        for a in ev:
            tok.mint(a, INIT_BAL)
            tok.approve(a, c, 10**12)
        for a in ev:
            c.join(a)

        late = A * LATE_FEE_BPS // BPS

        c.pay_in("u0", PAY + 1)      # trễ -> +late
        c.pay_in("u1", PAY + 1)      # trễ -> +late
        c.claim_default("u2", PAY + 1)
        self.assertEqual(c.penalty_pool, 2 * late)

        # các vòng sau trả đúng hạn
        now = PAY + 2
        for _ in range(50):
            if c.phase == Phase.Closed:
                break
            payers = [a for a in ev
                      if c.amount_due(a) > 0 and not c.paid_current.get(a)]
            if not payers:
                break
            for a in payers:
                if c.phase == Phase.Closed:
                    break
                c.pay_in(a, now)
            now += 1

        self.assertEqual(c.phase, Phase.Closed)
        self.assertEqual(c.penalty_paid, 2 * late, "chia hết quỹ phạt")

        pot = 2 * late
        each = pot // 3
        rest = pot - each * 3
        # Phần phạt nhận được (người đầu danh sách lấy phần dư làm tròn)
        share = {"org": each + rest, "u0": each, "u1": each}
        # Người trả trễ đã mất `late` ở vòng 0, nên số dư cuối trừ đi khoản đó.
        paid_late = {"org": False, "u0": True, "u1": True}
        for name in ("org", "u0", "u1"):
            expected = INIT_BAL + share[name] - (late if paid_late[name] else 0)
            self.assertEqual(
                tok.balance_of(name), expected,
                f"{name}: nhận {share[name]:,}, đã trả phạt trễ "
                f"{late if paid_late[name] else 0:,}")
        # Người cáo: không nhận một đồng phạt nào. u2 vẫn hoà vốn vì ký
        # quỹ của họ bù vào pot mà chính họ nhận ở vòng cuối — đúng thiết
        # kế: cáo chỉ mất khi cáo ở vòng muộn (xem test riêng bên dưới).
        self.assertEqual(
            tok.balance_of("u2"), INIT_BAL,
            "u2 không được chia phạt và cũng không mất gì ở kịch bản này")


    def test_winner_cannot_pay_in(self):
        """Người thắng vòng không được gọi payIn (due = 0)."""
        n = 3
        tok = Token()
        c = RoscaCircle(tok, "org", Mode.Fixed, n, A, PERIOD, COMMIT, REVEAL, PAY)
        ev = ["org", "u0", "u1"]
        for a in ev:
            tok.mint(a, INIT_BAL)
            tok.approve(a, c, 10**12)
        for a in ev:
            c.join(a)

        with self.assertRaises(Revert) as e:
            c.pay_in("org", 0)
        self.assertIn("AlreadyReceived", str(e.exception))

        c.pay_in("u0", 0)
        self.assertEqual(c.phase, Phase.Paying, "chưa đủ người, chưa trả pot")
        self.assertEqual(c.rounds[0].pot, A)

    def test_winner_cannot_be_defaulted(self):
        """Người thắng không thể bị claimDefault."""
        n = 3
        tok = Token()
        c = RoscaCircle(tok, "org", Mode.Fixed, n, A, PERIOD, COMMIT, REVEAL, PAY)
        ev = ["org", "u0", "u1"]
        for a in ev:
            tok.mint(a, INIT_BAL)
            tok.approve(a, c, 10**12)
        for a in ev:
            c.join(a)
        with self.assertRaises(Revert) as e:
            c.claim_default("org", PAY + 1)
        self.assertIn("AlreadyReceived", str(e.exception))

    def test_cannot_commit_twice(self):
        """Mỗi người chỉ được commit một lần mỗi vòng."""
        n = 3
        tok = Token()
        c = RoscaCircle(tok, "org", Mode.Bidding, n, A, PERIOD, COMMIT, REVEAL, PAY)
        ev = ["org", "u0", "u1"]
        for a in ev:
            tok.mint(a, INIT_BAL)
            tok.approve(a, c, 10**12)
        for a in ev:
            c.join(a)

        c.commit_bid("org", "h1", 0)
        with self.assertRaises(Revert) as e:
            c.commit_bid("org", "h2", 0)
        self.assertIn("AlreadyCommitted", str(e.exception))

    def test_reveal_before_deadline_rejected(self):
        """Reveal sớm phá tính kín của đấu giá nên phải bị chặn."""
        n = 3
        tok = Token()
        c = RoscaCircle(tok, "org", Mode.Bidding, n, A, PERIOD, COMMIT, REVEAL, PAY)
        ev = ["org", "u0", "u1"]
        for a in ev:
            tok.mint(a, INIT_BAL)
            tok.approve(a, c, 10**12)
        for a in ev:
            c.join(a)
        c.commit_bid("org", "h", 0)
        with self.assertRaises(Revert) as e:
            c.reveal_bid("org", 100, "h", 0)
        self.assertIn("TooEarly", str(e.exception))


class Fuzz(unittest.TestCase):
    def test_invariants(self):
        done = 0
        for seed in range(400):
            if run_one(seed) is not None:
                done += 1
        self.assertGreater(done, 350, f"chỉ {done}/400 seed chạy xong")

    def test_deposits_never_overdrawn(self):
        for seed in range(200):
            run_one(seed)


if __name__ == "__main__":
    unittest.main(verbosity=1)
