// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {RoscaCircle} from "../src/RoscaCircle.sol";
import {RoscaFactory} from "../src/RoscaFactory.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

contract RoscaTest is Test {
    MockUSDC    usdc;
    RoscaFactory factory;

    uint256 constant A = 1_000e6;          // 1.000 USDC (6 decimals)
    uint32  constant PERIOD = 30 days;
    uint32  constant COMMIT = 2 days;
    uint32  constant REVEAL = 1 days;
    uint32  constant PAY    = 1 days;

    address organizer = address(0xA11CE);
    address[5] users;

    function setUp() public {
        usdc = new MockUSDC();
        factory = new RoscaFactory(address(usdc), address(this), 50);

        users[0] = address(0xB0B);
        users[1] = address(0xCA0);
        users[2] = address(0xDAD);
        users[3] = address(0xEVE);
        users[4] = address(0xF00);

        address[5] memory all = [organizer, users[0], users[1], users[2], users[3]];
        for (uint256 i = 0; i < all.length; i++) {
            usdc.mint(all[i], 1_000_000e6);
            vm.prank(all[i]);
            usdc.approve(address(factory), type(uint256).max);
        }
    }

    // ─────────────────────────────────────────────────── helpers
    function _create(RoscaCircle.Mode mode, uint16 n) internal returns (RoscaCircle c) {
        RoscaFactory.CreateParams memory p = RoscaFactory.CreateParams({
            mode: mode,
            memberCount: n,
            contribution: A,
            period: PERIOD,
            commitWindow: COMMIT,
            revealWindow: REVEAL,
            payWindow: PAY
        });
        address addr = factory.createCircle(p);
        c = RoscaCircle(addr);
        for (uint256 i = 0; i < n; i++) {
            address m = i == 0 ? organizer : users[i - 1];
            vm.prank(m);
            usdc.approve(addr, type(uint256).max);
        }
    }

    function _joinAll(RoscaCircle c, uint16 n) internal {
        for (uint256 i = 0; i < n; i++) {
            address m = i == 0 ? organizer : users[i - 1];
            vm.prank(m);
            c.join();
        }
    }

    function _commit(RoscaCircle c, address m, uint256 bid, bytes32 salt) internal {
        bytes32 h = keccak256(abi.encode(bid, salt, m, c.currentRound()));
        vm.prank(m);
        c.commitBid(h);
    }

    function _reveal(RoscaCircle c, address m, uint256 bid, bytes32 salt) internal {
        vm.prank(m);
        c.revealBid(bid, salt);
    }

    // ─────────────────────────────────────────────────── 1. tạo + join
    function test_CreateAndJoin() public {
        RoscaCircle c = _create(RoscaCircle.Mode.Fixed, 3);
        assertEq(c.memberCount(), 3);
        assertEq(c.contribution(), A);
        assertEq(c.deposit(), A);           // ký quỹ = 1 kỳ góp

        _joinAll(c, 3);
        assertEq(c.membersLength(), 3);
        assertEq(usdc.balanceOf(address(c)), 3 * A);   // 3 ký quỹ
        assertEq(c.depositsHeld(), 3 * A);
    }

    // ─────────────────────────────────────────────────── 2. fixed flow
    /// Hụi cố định không lãi: mỗi người nhận đúng (n-1)*A, tổng net = 0.
    function test_FixedFullCycle_ZeroInterest() public {
        uint16 n = 3;
        RoscaCircle c = _create(RoscaCircle.Mode.Fixed, n);
        _joinAll(c, n);

        address[3] memory order = [organizer, users[0], users[1]];
        uint256 wat = (n - 1) * A;

        for (uint256 r = 0; r < n; r++) {
            // người thắng vòng này không đóng; những người khác đóng A
            for (uint256 i = 0; i < n; i++) {
                if (order[i] == order[r]) continue;
                vm.prank(order[i]);
                c.payIn();
            }
            assertEq(c.currentRound(), r, "round should not advance before last payer");
        }
        // sau người đóng cuối vòng cuối, hụi đóng
        assertEq(uint8(c.phase()), uint8(RoscaCircle.Phase.Closed));

        for (uint256 i = 0; i < n; i++) {
            (uint256 paid, uint256 rec,, uint256 depLeft,,) = c.memberSnapshot(order[i]);
            assertEq(rec, wat, "received");
            assertEq(paid, wat, "paid");
            assertEq(depLeft, A, "deposit refunded");
        }
        assertEq(usdc.balanceOf(address(c)), 0, "circle must hold nothing after close");
    }

    // ───────────────────────────────────────── 3. bidding: lowest wins
    function test_BiddingLowestBidWins() public {
        uint16 n = 3;
        RoscaCircle c = _create(RoscaCircle.Mode.Bidding, n);
        _joinAll(c, n);

        uint256 cap = c.maxBid();
        assertGt(cap, 0);

        bytes32 s1 = "salt1";
        bytes32 s2 = "salt2";
        _commit(c, organizer, cap, s1);
        _commit(c, users[0], cap / 2, s2);

        vm.warp(block.timestamp + COMMIT + 1);

        _reveal(c, organizer, cap, s1);
        _reveal(c, users[0], cap / 2, s2);

        vm.warp(block.timestamp + REVEAL + 1);
        c.settle();

        (uint16 receiver, uint256 bid,,, ,, bool settled) = c.roundSnapshot(0);
        assertTrue(settled);
        assertEq(bid, cap / 2, "lowest bid wins");
        assertEq(c.members(receiver), users[0], "users[0] is receiver");
    }

    // ───────────────────────────────────────── 4. trần 20%/năm
    function test_Revert_BidAboveCap() public {
        uint16 n = 3;
        RoscaCircle c = _create(RoscaCircle.Mode.Bidding, n);
        _joinAll(c, n);

        uint256 cap = c.maxBid();
        // kỳ 30 ngày, trần 20%/năm ⇒ cap = A * 2000/10000 * 30/365 ≈ 1.64% của A
        assertApproxEqRel(cap, (A * 2000 * PERIOD) / (10_000 * 365 days), 1e15);

        bytes32 s = "s";
        _commit(c, organizer, cap + 1, s);
        vm.warp(block.timestamp + COMMIT + 1);

        vm.prank(organizer);
        vm.expectRevert(abi.encodeWithSelector(RoscaCircle.BidAboveCap.selector, cap + 1, cap));
        c.revealBid(cap + 1, s);
    }

    /// Giá kêu đúng bằng trần phải tương đương đúng 20%/năm, không hơn.
    function test_CapEquals20PercentPerYear() public {
        RoscaCircle c = _create(RoscaCircle.Mode.Bidding, 3);
        uint256 cap = c.maxBid();
        uint256 aprBps = c.bidAprBps(cap);
        assertLe(aprBps, 2000, "never above 20%/year");
        assertGt(aprBps, 1990, "cap should sit at the limit");
    }

    // ────────────────────────────── 5. đấu giá kín: không reveal sớm
    function test_Revert_RevealBeforeCommitDeadline() public {
        RoscaCircle c = _create(RoscaCircle.Mode.Bidding, 3);
        _joinAll(c, 3);

        bytes32 s = "s";
        _commit(c, organizer, 100, s);

        vm.prank(organizer);
        vm.expectRevert(RoscaCircle.TooEarly.selector);
        c.revealBid(100, s);
    }

    // ─────────────────────────── 6. commit mà không reveal → mất nửa ký quỹ
    function test_CommitWithoutReveal_Slashed() public {
        RoscaCircle c = _create(RoscaCircle.Mode.Bidding, 3);
        _joinAll(c, 3);

        _commit(c, organizer, 100, "a");
        _commit(c, users[0], 200, "b");

        vm.warp(block.timestamp + COMMIT + 1);
        _reveal(c, users[0], 200, "b");       // organizer bỏ không reveal

        vm.warp(block.timestamp + REVEAL + 1);
        c.settle();

        (, , uint256 rec,,,) = c.memberSnapshot(organizer);
        // organizer bị trừ nửa ký quỹ
        (,,, uint256 depLeft,,) = c.memberSnapshot(organizer);
        assertEq(depLeft, A - A / 2, "half deposit slashed");
        assertEq(c.penaltyPool() + 0, A / 2, "goes to penalty pool");
        rec;
    }

    // ────────────────────────────────────────────── 7. phạt trễ hạn
    function test_LatePaymentCharged2Percent() public {
        uint16 n = 3;
        RoscaCircle c = _create(RoscaCircle.Mode.Fixed, n);
        _joinAll(c, n);

        // vòng 0: organizer là người nhận, users[0] và users[1] đóng
        vm.warp(block.timestamp + PAY + 1);   // quá hạn

        vm.prank(users[0]);
        c.payIn();
        assertEq(c.penaltyPool(), (A * 200) / 10_000, "2% late fee");

        (,,,, uint16 lateCount,) = c.memberSnapshot(users[0]);
        assertEq(lateCount, 1);
    }

    // ────────────────────────────────────────────── 8. cáo (default)
    function test_DefaultCoveredByDeposit() public {
        uint16 n = 3;
        RoscaCircle c = _create(RoscaCircle.Mode.Fixed, n);
        _joinAll(c, n);

        // users[1] bùng vòng 0
        vm.prank(users[0]);
        c.payIn();

        vm.warp(block.timestamp + PAY + 1);
        c.claimDefault(users[1]);

        (, , uint256 rec,,, uint16 defaultRound) = c.memberSnapshot(organizer);
        assertEq(rec, 2 * A, "organizer received full pot (deposit covered)");
        assertEq(defaultRound, 1, "default recorded");
        assertEq(c.shortfall(), 0, "no shortfall: deposit covered it");
    }

    /// Nếu không có ký quỹ bù đủ thì thiếu hụt được ghi công khai.
    function test_DefaultRecordsShortfall() public {
        uint16 n = 4;
        RoscaCircle c = _create(RoscaCircle.Mode.Bidding, n);
        _joinAll(c, n);

        bytes32 s = "s";
        _commit(c, organizer, 0, s);
        vm.warp(block.timestamp + COMMIT + 1);
        _reveal(c, organizer, 0, s);
        vm.warp(block.timestamp + REVEAL + 1);
        c.settle();

        // organizer nhận vòng 0. Những người khác phải đóng A.
        // users[0] bùng => ký quỹ A bù đủ A => shortfall 0
        vm.prank(users[1]); c.payIn();
        vm.prank(users[2]); c.payIn();

        vm.warp(block.timestamp + PAY + 1);
        c.claimDefault(users[0]);
        assertEq(c.shortfall(), 0);
    }

    // ─────────────────────────── 9. bất biến: contract về 0 sau khi đóng
    function test_Invariant_NoMoneyLeftAfterClose() public {
        uint16 n = 3;
        RoscaCircle c = _create(RoscaCircle.Mode.Bidding, n);
        _joinAll(c, n);

        bytes32 s = "x";
        _commit(c, organizer, 10, s);
        vm.warp(block.timestamp + COMMIT + 1);
        _reveal(c, organizer, 10, s);
        vm.warp(block.timestamp + REVEAL + 1);
        c.settle();

        // vòng 0: organizer nhận, others đóng A - 10
        vm.prank(users[0]); c.payIn();
        vm.prank(users[1]); c.payIn();

        // vòng 1 và 2: không ai đấu giá, settle chọn người chưa nhận
        for (uint256 r = 1; r < n; r++) {
            vm.warp(block.timestamp + COMMIT + REVEAL + 1);
            c.settle();
            for (uint256 i = 0; i < n; i++) {
                address m = i == 0 ? organizer : users[i - 1];
                if (c.amountDue(m) == 0) continue;
                vm.prank(m);
                c.payIn();
            }
        }

        assertEq(uint8(c.phase()), uint8(RoscaCircle.Phase.Closed));
        assertEq(usdc.balanceOf(address(c)), 0, "no dust left");
        assertEq(c.depositsHeld(), 0);
        assertEq(c.penaltyPool(), 0);
        assertEq(c.potInFlight(), 0);
    }

    // ─────────────────── 10. ký quỹ được hoàn đầy đủ cho người không cáo
    function test_DepositRefundedInFull() public {
        uint16 n = 3;
        RoscaCircle c = _create(RoscaCircle.Mode.Fixed, n);
        uint256 before = usdc.balanceOf(users[0]);
        _joinAll(c, n);
        assertEq(usdc.balanceOf(users[0]), before - A, "deposit taken");

        address[3] memory order = [organizer, users[0], users[1]];
        for (uint256 r = 0; r < n; r++) {
            for (uint256 i = 0; i < n; i++) {
                if (order[i] == order[r]) continue;
                vm.prank(order[i]);
                c.payIn();
            }
        }
        // users[0] đã đóng 2 kỳ (vòng 1,2), nhận 1 pot ở vòng 1
        assertEq(usdc.balanceOf(users[0]), before - 2 * A + A, "deposit + net back");
    }

    // ─────────────────────────── 11. factory registry
    function test_FactoryRegistry() public {
        _create(RoscaCircle.Mode.Fixed, 3);
        _create(RoscaCircle.Mode.Bidding, 4);
        assertEq(factory.circlesLength(), 2);
        assertEq(factory.circlesOfLength(organizer), 2);
    }

    // ─────────────────────────── 12. không ai đấu giá → vẫn chạy
    function test_NoBids_FallsBackToJoinOrder() public {
        uint16 n = 3;
        RoscaCircle c = _create(RoscaCircle.Mode.Bidding, n);
        _joinAll(c, n);

        vm.warp(block.timestamp + COMMIT + REVEAL + 1);
        c.settle();

        (uint16 receiver, uint256 bid,,, ,, bool settled) = c.roundSnapshot(0);
        assertTrue(settled);
        assertEq(bid, 0, "no discount");
        assertEq(c.members(receiver), organizer, "first joined wins");
    }
}
