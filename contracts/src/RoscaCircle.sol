// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/**
 * @title  RoscaCircle
 * @notice Một dây hụi on-chain (ROSCA). Pool bằng ERC-20 (USDC).
 *
 * ┌─ MÔ HÌNH KẾ TOÁN ────────────────────────────────────────────────────┐
 * │ n thành viên, mỗi vòng góp A, có n vòng, mỗi vòng một người nhận.    │
 * │                                                                     │
 * │   Người ĐÃ nhận hụi  ("hụi chết")  đóng:  A                          │
 * │   Người CHƯA nhận hụi ("hụi sống") đóng:  A - d   (d = giá thắng)    │
 * │   Người THẮNG vòng này             đóng:  0                          │
 * │                                                                     │
 * │   pot = (n-1)·(A-d) + (số người đã nhận trước đó)·d                  │
 * │   người thắng nhận đúng pot.                                         │
 * │                                                                     │
 * │ Vì sao hụi chết đóng A chứ không phải A+d: nếu đóng A+d thì tổng     │
 * │ thu mỗi vòng lớn hơn tổng chi — contract tự sinh ra tiền, bất khả    │
 * │ thi. Người nhận sớm "trả lãi" bằng việc nhận pot bị chiết khấu.      │
 * │ Hệ quả: tổng net của mọi thành viên = 0 theo từng vòng.              │
 * └─────────────────────────────────────────────────────────────────────┘
 *
 * ┌─ TRẦN LÃI SUẤT 20%/NĂM ─────────────────────────────────────────────┐
 * │ Bộ luật Dân sự 2015, Điều 468 chặn lãi suất thỏa thuận ở 20%/năm.   │
 * │ Giá kêu d là lãi trả thêm MỖI KỲ trên A, quy ra năm:                 │
 * │     apr = (d / A) · (YEAR / period)                                 │
 * │ nên giới hạn là  d ≤ A · 20% · period / YEAR  → xem `maxBid()`.      │
 * │ Giá kêu vượt trần bị revert, không bị cắt âm thầm.                   │
 * └─────────────────────────────────────────────────────────────────────┘
 *
 * ┌─ BA QUỸ TÁCH BIỆT ──────────────────────────────────────────────────┐
 * │ depositsHeld : ký quỹ còn giữ, hoàn khi đóng hụi.                    │
 * │ penaltyPool  : phí trễ hạn + ký quỹ bị slash, chia cho người         │
 * │                không cáo khi đóng hụi.                               │
 * │ pot (theo vòng): tiền đang gom cho người thắng vòng hiện tại.        │
 * │ Bất biến: balanceOf(this) == depositsHeld + penaltyPool + potInFlight│
 * └─────────────────────────────────────────────────────────────────────┘
 */
contract RoscaCircle {
    enum Mode  { Fixed, Bidding }
    enum Phase { Open, Bidding, Paying, Closed }

    struct Member {
        uint256 paidTotal;
        uint256 receivedTotal;
        uint256 slashed;
        uint16  wonRoundPlus1;     // 0 = chưa nhận; k = đã nhận ở vòng k
        uint16  lateCount;
        uint16  defaultRoundPlus1; // 0 = không cáo
        bool    hasCommitted;
        bool    hasRevealed;
    }

    struct Round {
        uint16  receiver;
        uint256 bid;
        uint256 pot;
        uint16  paidCount;
        uint16  outstandingCommits;
        uint40  commitDeadline;
        uint40  payDeadline;
        bool    settled;
    }

    uint256 public constant BPS          = 10_000;
    uint16  public constant MAX_APR_BPS  = 2_000;   // 20%/năm
    uint256 public constant YEAR         = 365 days;
    uint256 public constant LATE_FEE_BPS = 200;     // 2% kỳ góp mỗi lần trễ

    IERC20  public immutable usdc;
    address public immutable organizer;
    address public immutable factory;

    Mode    public immutable mode;
    uint16  public immutable memberCount;
    uint256 public immutable contribution;
    uint32  public immutable period;
    uint256 public immutable deposit;

    uint32 public immutable commitWindow;
    uint32 public immutable revealWindow;
    uint32 public immutable payWindow;

    address[] public members;
    mapping(address => Member)  public info;
    mapping(address => bool)    public isMember;
    mapping(address => bytes32) public commitment;
    mapping(address => uint256) public revealedBid;
    mapping(address => bool)    public paidCurrentRound;

    Round[] public rounds;
    uint16  public currentRound;
    Phase   public phase;

    uint256 public depositsHeld;
    uint256 public penaltyPool;
    uint256 public potInFlight;
    uint256 public shortfall;
    uint256 public yieldAccrued;

    bool private _locked;

    // ─────────────────────────────────────────────────────────── events
    event Joined(address indexed member, uint16 index);
    event PaidIn(address indexed member, uint16 indexed roundIdx, uint256 due, uint256 fee);
    event BidCommitted(address indexed member, uint16 indexed roundIdx, bytes32 h);
    event BidRevealed(address indexed member, uint16 indexed roundIdx, uint256 bid);
    event CircleSettled(uint16 indexed roundIdx, address indexed receiver, uint256 bid, uint256 pot);
    event Payout(address indexed receiver, uint16 indexed roundIdx, uint256 pot);
    event MemberDefaulted(address indexed member, uint16 indexed roundIdx, uint256 covered, uint256 short);
    event BidForfeited(address indexed member, uint16 indexed roundIdx, uint256 slashed);
    event CircleClosed(uint256 refunded, uint256 penaltyPaid, uint256 yieldPaid);
    event YieldAccrued(uint256 amount);

    // ─────────────────────────────────────────────────────────── errors
    error NotAuthorised();
    error AlreadyMember();
    error CircleFull();
    error WrongPhase();
    error TooEarly();
    error TooLate();
    error AlreadyCommitted();
    error NoCommitment();
    error BadReveal();
    error BidAboveCap(uint256 bid, uint256 cap);
    error AlreadyReceived();
    error AlreadyPaidIn();
    error TransferFailed();
    error Reentrancy();
    error BadParams();

    modifier nonReentrant() {
        if (_locked) revert Reentrancy();
        _locked = true;
        _;
        _locked = false;
    }

    modifier onlyMember() {
        if (!isMember[msg.sender]) revert NotAuthorised();
        _;
    }

    // ─────────────────────────────────────────────────────────── ctor
    constructor(
        address usdc_,
        address organizer_,
        Mode    mode_,
        uint16  memberCount_,
        uint256 contribution_,
        uint32  period_,
        uint32  commitWindow_,
        uint32  revealWindow_,
        uint32  payWindow_
    ) {
        if (memberCount_ < 2 || contribution_ == 0 || period_ == 0) revert BadParams();
        if (commitWindow_ == 0 || revealWindow_ == 0 || payWindow_ == 0) revert BadParams();

        usdc         = IERC20(usdc_);
        organizer    = organizer_;
        factory      = msg.sender;
        mode         = mode_;
        memberCount  = memberCount_;
        contribution = contribution_;
        period       = period_;
        deposit      = contribution_;   // ký quỹ = 1 kỳ góp

        commitWindow = commitWindow_;
        revealWindow = revealWindow_;
        payWindow    = payWindow_;

        phase = Phase.Open;
    }

    // ─────────────────────────────────────────────────────────── join
    function join() external nonReentrant {
        if (phase != Phase.Open) revert WrongPhase();
        if (isMember[msg.sender]) revert AlreadyMember();
        if (members.length >= memberCount) revert CircleFull();

        members.push(msg.sender);
        isMember[msg.sender] = true;

        depositsHeld += deposit;
        if (!usdc.transferFrom(msg.sender, address(this), deposit)) revert TransferFailed();
        emit Joined(msg.sender, uint16(members.length - 1));

        if (members.length == memberCount) {
            _pushRound();
            if (mode == Mode.Bidding) {
                _openCommit();
            } else {
                _startPaying(_firstUnpaidIndex(), 0);
            }
        }
    }

    // ────────────────────────────────────────────────────────── bidding
    /// @notice Cam kết giá kêu. Mở từ đầu kỳ đến `commitDeadline`.
    function commitBid(bytes32 h) external onlyMember nonReentrant {
        if (phase != Phase.Bidding) revert WrongPhase();
        Member storage m = info[msg.sender];
        if (block.timestamp > rounds[currentRound].commitDeadline) revert TooLate();
        if (m.wonRoundPlus1 != 0) revert AlreadyReceived();
        if (m.hasCommitted) revert AlreadyCommitted();

        commitment[msg.sender] = h;
        m.hasCommitted = true;
        rounds[currentRound].outstandingCommits += 1;
        emit BidCommitted(msg.sender, currentRound, h);
    }

    /**
     * @notice Mở giá kêu, chỉ trong cửa sổ reveal (sau commitDeadline).
     * @dev    Chặn reveal sớm là điều kiện để đấu giá thực sự kín: nếu cho
     *         reveal trước hạn, người sau thấy giá người trước và hết kín.
     */
    function revealBid(uint256 bid, bytes32 salt) external onlyMember nonReentrant {
        if (phase != Phase.Bidding) revert WrongPhase();
        Round storage r = rounds[currentRound];
        if (block.timestamp < r.commitDeadline) revert TooEarly();
        if (block.timestamp > uint256(r.commitDeadline) + revealWindow) revert TooLate();

        bytes32 c = commitment[msg.sender];
        if (c == bytes32(0)) revert NoCommitment();
        if (keccak256(abi.encode(bid, salt, msg.sender, currentRound)) != c) revert BadReveal();

        uint256 cap = maxBid();
        if (bid > cap) revert BidAboveCap(bid, cap);

        info[msg.sender].hasRevealed = true;
        revealedBid[msg.sender] = bid;
        r.outstandingCommits -= 1;
        emit BidRevealed(msg.sender, currentRound, bid);
    }

    /**
     * @notice Chốt vòng sau khi hết cửa sổ reveal.
     *         Giá thấp nhất thắng; hoà thì người tham gia sớm hơn thắng.
     *         Không ai mở giá → chọn người chưa nhận có thứ tự join nhỏ nhất.
     *         Ai commit mà không reveal bị trừ nửa ký quỹ vào `penaltyPool`.
     */
    function settle() external nonReentrant {
        if (phase != Phase.Bidding) revert WrongPhase();
        Round storage r = rounds[currentRound];
        if (block.timestamp <= uint256(r.commitDeadline) + revealWindow) revert TooEarly();

        for (uint256 i = 0; i < members.length; i++) {
            address m = members[i];
            Member storage mi = info[m];
            if (mi.hasCommitted && !mi.hasRevealed) {
                uint256 take = deposit / 2;
                _slashToPenalty(m, take);
                emit BidForfeited(m, currentRound, take);
            }
            delete commitment[m];
        }

        uint256 best   = type(uint256).max;
        uint16  winner = type(uint16).max;
        bool    found;

        for (uint256 i = 0; i < members.length; i++) {
            address m = members[i];
            if (info[m].wonRoundPlus1 != 0) continue;
            if (!info[m].hasRevealed) continue;
            uint256 b = revealedBid[m];
            if (!found || b < best) { best = b; winner = uint16(i); found = true; }
        }

        _startPaying(found ? winner : _firstUnpaidIndex(), found ? best : 0);
    }

    function _startPaying(uint16 w, uint256 bid) internal {
        Round storage r = rounds[currentRound];
        r.receiver     = w;
        r.bid          = bid;
        r.settled      = true;
        r.payDeadline  = uint40(block.timestamp) + payWindow;
        info[members[w]].wonRoundPlus1 = currentRound + 1;
        phase = Phase.Paying;
        emit CircleSettled(currentRound, members[w], bid, r.pot);
    }

    // ─────────────────────────────────────────────────────────── pay in
    /**
     * @notice Số tiền phải đóng ở vòng hiện tại, chưa gồm phạt trễ.
     *         Người thắng vòng này trả 0.
     */
    function amountDue(address m) public view returns (uint256) {
        if (phase != Phase.Paying) return 0;
        if (!isMember[m]) return 0;
        if (members[rounds[currentRound].receiver] == m) return 0;
        if (info[m].wonRoundPlus1 != 0) return contribution;

        uint256 d = rounds[currentRound].bid;
        return d >= contribution ? 0 : contribution - d;
    }

    function payIn() external onlyMember nonReentrant {
        if (phase != Phase.Paying) revert WrongPhase();
        if (paidCurrentRound[msg.sender]) revert AlreadyPaidIn();

        Round storage r = rounds[currentRound];
        uint256 due = amountDue(msg.sender);

        // Người thắng vòng này đóng 0. Cho họ gọi payIn sẽ chiếm mất một
        // slot trong `paidCount`, khiến pot được trả khi vẫn còn người
        // chưa đóng -> thiếu tiền. Chặn thẳng.
        if (due == 0) revert AlreadyReceived();

        uint256 fee;
        if (block.timestamp > r.payDeadline) {
            fee = (contribution * LATE_FEE_BPS) / BPS;
            info[msg.sender].lateCount += 1;
            penaltyPool += fee;
        }

        paidCurrentRound[msg.sender] = true;
        info[msg.sender].paidTotal += due;
        r.paidCount += 1;
        r.pot += due;
        potInFlight += due;

        uint256 charge = due + fee;
        if (!usdc.transferFrom(msg.sender, address(this), charge)) revert TransferFailed();
        emit PaidIn(msg.sender, currentRound, due, fee);

        if (r.paidCount == memberCount - 1) _payout();
    }

    /**
     * @notice Ai đó không đóng, hết `payDeadline` → bất kỳ ai gọi được.
     *         Ký quỹ của họ bù vào pot; phần thiếu ghi vào `shortfall`
     *         (công khai, hiện trên dashboard, không giấu).
     */
    function claimDefault(address who) external nonReentrant {
        if (phase != Phase.Paying) revert WrongPhase();
        Round storage r = rounds[currentRound];
        if (block.timestamp <= r.payDeadline) revert TooEarly();
        if (!isMember[who]) revert NotAuthorised();
        if (paidCurrentRound[who]) revert AlreadyPaidIn();

        uint256 due       = amountDue(who);
        if (due == 0) revert AlreadyReceived();
        uint256 available = deposit - info[who].slashed;
        uint256 covered   = due < available ? due : available;

        info[who].slashed += covered;
        info[who].defaultRoundPlus1 = currentRound + 1;
        depositsHeld -= covered;

        paidCurrentRound[who] = true;
        r.paidCount += 1;
        r.pot += covered;
        potInFlight += covered;

        if (due > covered) shortfall += due - covered;
        emit MemberDefaulted(who, currentRound, covered, due - covered);

        if (r.paidCount == memberCount - 1) _payout();
    }

    function _payout() internal {
        Round storage r = rounds[currentRound];
        address w = members[r.receiver];
        uint256 pot = r.pot;

        info[w].receivedTotal += pot;
        potInFlight -= pot;
        emit Payout(w, currentRound, pot);

        if (!usdc.transfer(w, pot)) revert TransferFailed();
        _nextRound();
    }

    function _nextRound() internal {
        uint16 next = currentRound + 1;

        for (uint256 i = 0; i < members.length; i++) {
            address m = members[i];
            paidCurrentRound[m] = false;
            info[m].hasCommitted = false;
            info[m].hasRevealed  = false;
            revealedBid[m] = 0;
        }

        if (next >= memberCount) { _close(); return; }

        currentRound = next;
        _pushRound();

        if (mode == Mode.Bidding) {
            _openCommit();
        } else {
            _startPaying(_firstUnpaidIndex(), 0);
        }
    }

    // ─────────────────────────────────────────────────────────── close
    function _close() internal {
        phase = Phase.Closed;

        // Chia quỹ phạt cho người không cáo; nếu tất cả đều cáo thì chia đều.
        uint256 penalty = penaltyPool;
        if (penalty > 0) {
            uint256 eligible;
            for (uint256 i = 0; i < members.length; i++) {
                if (info[members[i]].defaultRoundPlus1 == 0) eligible++;
            }
            if (eligible == 0) eligible = memberCount;

            uint256 share    = penalty / eligible;
            uint256 rest     = penalty - share * eligible;
            uint256 given;
            for (uint256 i = 0; i < members.length; i++) {
                address m = members[i];
                if (eligible != memberCount && info[m].defaultRoundPlus1 != 0) continue;
                uint256 amt = share;
                if (given == 0) amt += rest;     // dư làm tròn cho người đầu
                if (amt == 0) continue;
                given += amt;
                penaltyPool -= amt;
                if (!usdc.transfer(m, amt)) revert TransferFailed();
            }
            penaltyPool = 0;
        }

        // Hoàn ký quỹ còn lại
        uint256 refunded;
        for (uint256 i = 0; i < members.length; i++) {
            address m = members[i];
            uint256 left = deposit - info[m].slashed;
            if (left == 0) continue;
            depositsHeld -= left;
            refunded += left;
            if (!usdc.transfer(m, left)) revert TransferFailed();
        }

        // Yield (bonus) chia đều
        uint256 y = yieldAccrued;
        if (y > 0) {
            uint256 share = y / memberCount;
            uint256 rest  = y - share * memberCount;
            for (uint256 i = 0; i < members.length; i++) {
                uint256 amt = share + (i == 0 ? rest : 0);
                if (amt == 0) continue;
                if (!usdc.transfer(members[i], amt)) revert TransferFailed();
            }
            yieldAccrued = 0;
        }

        emit CircleClosed(refunded, penalty, y);
    }

    // ────────────────────────────────────────────────────────── intern
    function _pushRound() internal {
        rounds.push(Round({
            receiver: 0, bid: 0, pot: 0,
            paidCount: 0, outstandingCommits: 0,
            commitDeadline: 0, payDeadline: 0, settled: false
        }));
    }

    function _openCommit() internal {
        rounds[currentRound].commitDeadline = uint40(block.timestamp) + commitWindow;
        phase = Phase.Bidding;
    }

    function _firstUnpaidIndex() internal view returns (uint16) {
        for (uint256 i = 0; i < members.length; i++) {
            if (info[members[i]].wonRoundPlus1 == 0) return uint16(i);
        }
        return 0;
    }

    /// @dev Chỉ dùng cho ký quỹ bị phạt, không đụng tới pot.
    function _slashToPenalty(address m, uint256 amount) internal {
        uint256 left = deposit - info[m].slashed;
        if (amount > left) amount = left;
        if (amount == 0) return;
        info[m].slashed += amount;
        depositsHeld  -= amount;
        penaltyPool   += amount;
    }

    /**
     * @notice Trần giá kêu theo 20%/năm trên một đơn vị góp.
     * @dev    d ≤ A · MAX_APR_BPS · period / (BPS · YEAR)
     */
    function maxBid() public view returns (uint256) {
        return (contribution * MAX_APR_BPS * period) / (BPS * YEAR);
    }

    /// @notice Quy đổi giá kêu ra APR (bps) để hiển thị.
    function bidAprBps(uint256 bid) public view returns (uint256) {
        return (bid * BPS * YEAR) / (contribution * period);
    }

    // ─────────────────────────────────────────────────────────── views
    function membersLength() external view returns (uint256) { return members.length; }
    function roundsLength()  external view returns (uint256) { return rounds.length; }

    function memberSnapshot(address m)
        external view
        returns (uint256 paidTotal, uint256 receivedTotal, uint16 wonRoundPlus1,
                 uint256 depositLeft, uint16 lateCount, uint16 defaultRoundPlus1)
    {
        Member storage i = info[m];
        return (i.paidTotal, i.receivedTotal, i.wonRoundPlus1,
                deposit - i.slashed, i.lateCount, i.defaultRoundPlus1);
    }

    function roundSnapshot(uint16 k)
        external view
        returns (uint16 receiver, uint256 bid, uint256 pot, uint16 paidCount,
                 uint40 commitDeadline, uint40 payDeadline, bool settled)
    {
        Round storage r = rounds[k];
        return (r.receiver, r.bid, r.pot, r.paidCount,
                r.commitDeadline, r.payDeadline, r.settled);
    }

    /// @notice Ghi nhận yield từ adapter (bonus). Contract không tự đầu tư.
    function noteYield(uint256 amount) external {
        if (msg.sender != factory && msg.sender != organizer) revert NotAuthorised();
        yieldAccrued += amount;
        emit YieldAccrued(amount);
    }

    /// @notice Tổng tiền contract đang giữ (phải khớp balanceOf).
    function totalPool() external view returns (uint256) {
        return depositsHeld + penaltyPool + potInFlight;
    }
}
