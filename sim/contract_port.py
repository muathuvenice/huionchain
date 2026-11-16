"""
Port 1-1 của RoscaCircle.sol sang Python, dùng để kiểm chứng logic
khi không có forge. Mỗi hàm ở đây tương ứng một hàm Solidity cùng tên.
State machine, guard, và ba quỹ (depositsHeld / penaltyPool / potInFlight)
phải khớp tuyệt đối.

Đây KHÔNG phải mô hình lý tưởng hoá - nó cố tình bắt chước cả những
chỗ dễ sai trong Solidity (thứ tự cập nhật state, chặn winner payIn,
tính phí trễ, chia quỹ phạt).
"""
from enum import Enum

BPS = 10_000
MAX_APR_BPS = 2_000
YEAR = 365 * 86400
LATE_FEE_BPS = 200


class Mode(Enum):
    Fixed = 0
    Bidding = 1


class Phase(Enum):
    Open = 0
    Bidding = 1
    Paying = 2
    Closed = 3


class Revert(Exception):
    pass


class Member:
    def __init__(self):
        self.paid_total = 0
        self.received_total = 0
        self.slashed = 0
        self.won_round_plus1 = 0
        self.late_count = 0
        self.default_round_plus1 = 0
        self.has_committed = False
        self.has_revealed = False


class Round:
    def __init__(self):
        self.receiver = 0
        self.bid = 0
        self.pot = 0
        self.paid_count = 0
        self.outstanding_commits = 0
        self.commit_deadline = 0
        self.pay_deadline = 0
        self.settled = False


class Token:
    def __init__(self):
        self.bal = {}
        self.appr = {}

    def mint(self, a, amt):
        self.bal[a] = self.bal.get(a, 0) + amt

    def approve(self, owner, spender, amt):
        self.appr[(owner, spender)] = amt

    def balance_of(self, a):
        return self.bal.get(a, 0)

    def transfer_from(self, frm, to, amt):
        if self.bal.get(frm, 0) < amt:
            raise Revert("balance")
        if self.appr.get((frm, to), 0) < amt:
            raise Revert("allowance")
        self.bal[frm] -= amt
        self.bal[to] = self.bal.get(to, 0) + amt
        return True

    def transfer(self, frm, to, amt):
        if self.bal.get(frm, 0) < amt:
            raise Revert("balance")
        self.bal[frm] -= amt
        self.bal[to] = self.bal.get(to, 0) + amt
        return True


class RoscaCircle:
    def __init__(self, usdc, organizer, mode, n, contribution, period,
                 commit_window, reveal_window, pay_window):
        if n < 2 or contribution == 0 or period == 0:
            raise Revert("BadParams")
        self.usdc = usdc
        self.organizer = organizer
        self.mode = mode
        self.n = n
        self.A = contribution
        self.period = period
        self.deposit = contribution
        self.commit_window = commit_window
        self.reveal_window = reveal_window
        self.pay_window = pay_window

        self.members = []
        self.info = {}
        self.commitment = {}
        self.revealed_bid = {}
        self.paid_current = {}
        self.rounds = []
        self.current_round = 0
        self.phase = Phase.Open
        self.deposits_held = 0
        self.penalty_pool = 0
        self.pot_in_flight = 0
        self.shortfall = 0
        self.yield_accrued = 0
        self.penalty_paid = 0     # tổng quỹ phạt đã chia khi đóng hụi
        self.round_dues = []       # tổng `due` đã đóng mỗi vòng (không gồm phí trễ)

    # ---------------------------------------------------------- helpers
    def _m(self, a):
        return self.info.setdefault(a, Member())

    def max_bid(self):
        return self.A * MAX_APR_BPS * self.period // (BPS * YEAR)

    def bid_apr_bps(self, bid):
        return bid * BPS * YEAR // (self.A * self.period)

    def amount_due(self, a):
        if self.phase != Phase.Paying:
            return 0
        if a not in self.info:
            return 0
        r = self.rounds[self.current_round]
        if self.members[r.receiver] == a:
            return 0
        if self._m(a).won_round_plus1 != 0:
            return self.A
        d = r.bid
        return 0 if d >= self.A else self.A - d

    def _bump_dues(self, amount):
        while len(self.round_dues) <= self.current_round:
            self.round_dues.append(0)
        self.round_dues[self.current_round] += amount

    def _push_round(self):
        self.rounds.append(Round())
        while len(self.round_dues) <= self.current_round:
            self.round_dues.append(0)

    def _open_commit(self, now):
        r = self.rounds[self.current_round]
        r.commit_deadline = now + self.commit_window
        self.phase = Phase.Bidding

    def _first_unpaid(self):
        for i, a in enumerate(self.members):
            if self._m(a).won_round_plus1 == 0:
                return i
        return 0

    def _start_paying(self, w, bid, now):
        r = self.rounds[self.current_round]
        r.receiver = w
        r.bid = bid
        r.settled = True
        r.pay_deadline = now + self.pay_window
        self._m(self.members[w]).won_round_plus1 = self.current_round + 1
        self.phase = Phase.Paying

    def _slash_to_penalty(self, a, amount):
        m = self._m(a)
        left = self.deposit - m.slashed
        amount = min(amount, left)
        if amount == 0:
            return
        m.slashed += amount
        self.deposits_held -= amount
        self.penalty_pool += amount

    # ------------------------------------------------------------ join
    def join(self, who):
        if self.phase != Phase.Open:
            raise Revert("WrongPhase")
        if who in self.info:
            raise Revert("AlreadyMember")
        if len(self.members) >= self.n:
            raise Revert("CircleFull")

        self.members.append(who)
        self._m(who)
        self.deposits_held += self.deposit
        self.usdc.transfer_from(who, self, self.deposit)

        if len(self.members) == self.n:
            self._push_round()
            if self.mode == Mode.Bidding:
                self._open_commit(0)
            else:
                self._start_paying(self._first_unpaid(), 0, 0)

    # --------------------------------------------------------- bidding
    def commit_bid(self, who, h, now):
        if self.phase != Phase.Bidding:
            raise Revert("WrongPhase")
        m = self._m(who)
        if now > self.rounds[self.current_round].commit_deadline:
            raise Revert("TooLate")
        if m.won_round_plus1 != 0:
            raise Revert("AlreadyReceived")
        if m.has_committed:
            raise Revert("AlreadyCommitted")
        self.commitment[who] = h
        m.has_committed = True
        self.rounds[self.current_round].outstanding_commits += 1

    def reveal_bid(self, who, bid, salt_h, now):
        if self.phase != Phase.Bidding:
            raise Revert("WrongPhase")
        r = self.rounds[self.current_round]
        if now < r.commit_deadline:
            raise Revert("TooEarly")
        if now > r.commit_deadline + self.reveal_window:
            raise Revert("TooLate")
        c = self.commitment.get(who)
        if not c:
            raise Revert("NoCommitment")
        if c != salt_h:
            raise Revert("BadReveal")
        cap = self.max_bid()
        if bid > cap:
            raise Revert(f"BidAboveCap({bid},{cap})")
        self._m(who).has_revealed = True
        self.revealed_bid[who] = bid
        r.outstanding_commits -= 1

    def settle(self, now):
        if self.phase != Phase.Bidding:
            raise Revert("WrongPhase")
        r = self.rounds[self.current_round]
        if now <= r.commit_deadline + self.reveal_window:
            raise Revert("TooEarly")

        for a in self.members:
            m = self._m(a)
            if m.has_committed and not m.has_revealed:
                self._slash_to_penalty(a, self.deposit // 2)
            self.commitment.pop(a, None)

        best, winner, found = None, None, False
        for i, a in enumerate(self.members):
            if self._m(a).won_round_plus1 != 0:
                continue
            if not self._m(a).has_revealed:
                continue
            b = self.revealed_bid[a]
            if not found or b < best:
                best, winner, found = b, i, True

        self._start_paying(winner if found else self._first_unpaid(),
                           best if found else 0, now)

    # ---------------------------------------------------------- pay in
    def pay_in(self, who, now):
        if self.phase != Phase.Paying:
            raise Revert("WrongPhase")
        if self.paid_current.get(who):
            raise Revert("AlreadyPaidIn")

        r = self.rounds[self.current_round]
        due = self.amount_due(who)
        if due == 0:
            raise Revert("AlreadyReceived")

        fee = 0
        if now > r.pay_deadline:
            fee = self.A * LATE_FEE_BPS // BPS
            self._m(who).late_count += 1
            self.penalty_pool += fee

        self.paid_current[who] = True
        self._m(who).paid_total += due
        r.paid_count += 1
        r.pot += due
        self.pot_in_flight += due
        self._bump_dues(due)

        self.usdc.transfer_from(who, self, due + fee)
        if r.paid_count == self.n - 1:
            self._payout(now)

    def claim_default(self, who, now):
        if self.phase != Phase.Paying:
            raise Revert("WrongPhase")
        r = self.rounds[self.current_round]
        if now <= r.pay_deadline:
            raise Revert("TooEarly")
        if who not in self.info:
            raise Revert("NotAuthorised")
        if self.paid_current.get(who):
            raise Revert("AlreadyPaidIn")

        due = self.amount_due(who)
        if due == 0:
            raise Revert("AlreadyReceived")
        m = self._m(who)
        available = self.deposit - m.slashed
        covered = min(due, available)

        m.slashed += covered
        m.default_round_plus1 = self.current_round + 1
        self.deposits_held -= covered

        self.paid_current[who] = True
        r.paid_count += 1
        r.pot += covered
        self.pot_in_flight += covered
        self._bump_dues(covered)

        if due > covered:
            self.shortfall += due - covered

        if r.paid_count == self.n - 1:
            self._payout(now)

    def _payout(self, now):
        r = self.rounds[self.current_round]
        w = self.members[r.receiver]
        pot = r.pot
        self._m(w).received_total += pot
        self.pot_in_flight -= pot
        self.usdc.transfer(self, w, pot)
        self._next_round(now)

    def _next_round(self, now):
        nxt = self.current_round + 1
        for a in self.members:
            self.paid_current[a] = False
            m = self._m(a)
            m.has_committed = False
            m.has_revealed = False
            self.revealed_bid[a] = 0

        if nxt >= self.n:
            self._close()
            return

        self.current_round = nxt
        self._push_round()
        if self.mode == Mode.Bidding:
            self._open_commit(now)
        else:
            self._start_paying(self._first_unpaid(), 0, now)

    def _close(self):
        self.phase = Phase.Closed

        penalty = self.penalty_pool
        if penalty > 0:
            eligible = [a for a in self.members
                        if self._m(a).default_round_plus1 == 0]
            if not eligible:
                eligible = list(self.members)
            k = len(eligible)
            share = penalty // k
            rest = penalty - share * k
            given = 0
            for a in eligible:
                amt = share
                if given == 0:
                    amt += rest
                if amt == 0:
                    continue
                given += amt
                self.penalty_pool -= amt
                self.penalty_paid += amt
                self.usdc.transfer(self, a, amt)
            self.penalty_pool = 0

        for a in self.members:
            left = self.deposit - self._m(a).slashed
            if left == 0:
                continue
            self.deposits_held -= left
            self.usdc.transfer(self, a, left)

        y = self.yield_accrued
        if y > 0:
            share = y // self.n
            rest = y - share * self.n
            for i, a in enumerate(self.members):
                amt = share + (rest if i == 0 else 0)
                self.usdc.transfer(self, a, amt)
            self.yield_accrued = 0

    def total_pool(self):
        return self.deposits_held + self.penalty_pool + self.pot_in_flight
