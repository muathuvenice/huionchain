// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {RoscaCircle} from "./RoscaCircle.sol";

/**
 * @title  RoscaFactory
 * @notice Tạo và đăng ký các dây hụi. Không giữ tiền, không có quyền đặc biệt
 *         trên contract con — chủ hụi chỉ là người tạo, không phải người giữ quỹ.
 */
contract RoscaFactory {
    address public immutable usdc;
    address public feeRecipient;
    uint16  public feeBps;              // phí nền tảng, mặc định 0.5%

    address[] public circles;
    mapping(address => address[]) public circlesOf;   // organizer => circles
    mapping(address => bool)      public isCircle;

    event CircleCreated(
        address indexed circle,
        address indexed organizer,
        RoscaCircle.Mode mode,
        uint16  memberCount,
        uint256 contribution,
        uint32  period
    );
    event FeeUpdated(uint16 feeBps, address recipient);

    error NotOwner();

    address public owner;

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address usdc_, address feeRecipient_, uint16 feeBps_) {
        usdc         = usdc_;
        feeRecipient = feeRecipient_;
        feeBps       = feeBps_;
        owner        = msg.sender;
    }

    struct CreateParams {
        RoscaCircle.Mode mode;
        uint16  memberCount;
        uint256 contribution;
        uint32  period;
        uint32  commitWindow;
        uint32  revealWindow;
        uint32  payWindow;
    }

    /**
     * @notice Tạo dây hụi mới. Người gọi trở thành organizer.
     * @dev    Các cửa sổ thời gian do người tạo chọn để demo nhanh được
     *         (ví dụ commitWindow = 60 giây trên Fuji).
     */
    function createCircle(CreateParams calldata p) external returns (address circle) {
        circle = address(new RoscaCircle(
            usdc,
            msg.sender,
            p.mode,
            p.memberCount,
            p.contribution,
            p.period,
            p.commitWindow,
            p.revealWindow,
            p.payWindow
        ));

        circles.push(circle);
        circlesOf[msg.sender].push(circle);
        isCircle[circle] = true;

        emit CircleCreated(circle, msg.sender, p.mode,
                           p.memberCount, p.contribution, p.period);
    }

    function circlesLength() external view returns (uint256) {
        return circles.length;
    }

    function circlesOfLength(address organizer) external view returns (uint256) {
        return circlesOf[organizer].length;
    }

    function setFee(uint16 feeBps_, address recipient_) external onlyOwner {
        feeBps       = feeBps_;
        feeRecipient = recipient_;
        emit FeeUpdated(feeBps_, recipient_);
    }
}
