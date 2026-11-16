// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {MockUSDC}     from "../src/MockUSDC.sol";
import {RoscaFactory} from "../src/RoscaFactory.sol";
import {RoscaCircle}  from "../src/RoscaCircle.sol";

/**
 * @notice Cần biến môi trường: PRIVATE_KEY
 *
 * forge script script/Deploy.s.sol:DeployMockUSDC --rpc-url $FUJI_RPC --broadcast --private-key $PRIVATE_KEY
 */
contract DeployMockUSDC is Script {
    function run() external returns (MockUSDC usdc) {
        vm.startBroadcast(vm.envUint("PRIVATE_KEY"));
        usdc = new MockUSDC();
        console2.log("MockUSDC", address(usdc));
        vm.stopBroadcast();
    }
}

/**
 * forge script script/Deploy.s.sol:DeployFactory \
 *   --rpc-url $FUJI_RPC --broadcast --private-key $PRIVATE_KEY \
 *   --sig "run(address,address,uint16)" $MOCK_USDC $WALLET 50
 */
contract DeployFactory is Script {
    function run(address usdc, address feeRecipient, uint16 feeBps)
        external
        returns (RoscaFactory factory)
    {
        vm.startBroadcast(vm.envUint("PRIVATE_KEY"));
        factory = new RoscaFactory(usdc, feeRecipient, feeBps);
        console2.log("RoscaFactory", address(factory));
        vm.stopBroadcast();
    }
}

/**
 * Tạo dây hụi mẫu 4 người, đấu giá kín, 1 kỳ = 1 triệu USDC-unit.
 *
 * forge script script/Deploy.s.sol:CreateSampleCircle \
 *   --rpc-url $FUJI_RPC --broadcast --private-key $PRIVATE_KEY \
 *   --sig "run(address)" $FACTORY
 *
 * Cửa sổ thời gian để demo nhanh: commit 120s, reveal 120s, pay 300s.
 * period 10 phút (chỉ để demo) — KHÔNG dùng cho dây hụi thật.
 */
contract CreateSampleCircle is Script {
    function run(address factory) external returns (address circle) {
        RoscaFactory f = RoscaFactory(factory);

        RoscaFactory.CreateParams memory p = RoscaFactory.CreateParams({
            mode:         RoscaCircle.Mode.Bidding,
            memberCount:  4,
            contribution: 1_000_000,   // 1 USDC (6 chữ số thập phân)
            period:       10 minutes,
            commitWindow: 120,
            revealWindow: 120,
            payWindow:    300
        });

        vm.startBroadcast(vm.envUint("PRIVATE_KEY"));
        circle = f.createCircle(p);
        console2.log("RoscaCircle", circle);
        vm.stopBroadcast();
    }
}
