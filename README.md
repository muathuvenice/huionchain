# Hụi On-Chain

**ROSCA** (rotating savings and credit association) trên Avalanche C-Chain —
hợp đồng thay chủ hụi, tiền không nằm trong tay ai cả.

---

## Cấu trúc thư mục

```
contracts/        Solidity 0.8.24 + Foundry
  src/
    RoscaCircle.sol   hợp đồng chính (pool / rounds / bidding / penalty / payout)
    RoscaFactory.sol  tạo và đăng ký dây hụi
    MockUSDC.sol      ERC-20 giả để test trên Fuji
  test/
    Rosca.t.sol       14 test Foundry (unit + fuzz)
  foundry.toml

sim/              Mô hình Python 1:1 với Solidity (spec có thể chạy được)
  rosca_model.py      spec kinh tế, giải thích tại sao hụi chết trả A không A+d
  contract_port.py    state machine Python mirror của Solidity
  test_contract_port.py  15 scenario test
  test_fuzz.py        fuzz 400 seed, 6 bất biến, mutation testing 15/15

app/              Giao diện Streamlit + Web3.py
  main.py             6 tab UI: Tổng quan / Đóng hụi / Đấu giá / Lịch sử / Điểm uy tín / Trợ lý AI
  chain.py            đọc contract state, build transaction
  agent_bridge.py     nối dữ liệu on-chain vào AI agent
  contract_abi.py     ABI tối giản cho RoscaCircle + RoscaFactory + ERC-20
  test_logic.py       15 test logic UI & bridge (không cần network)

ai/
  agent.py            vòng lặp AI agent + guardrail chống bịa số
  tools.py            bộ công cụ tính toán deterministic cho agent
  llm.py              REST client cho Gemini (gemini-2.0-flash)
  credit_score.py     điểm uy tín từ dữ liệu on-chain (không dùng LLM)
  test_agent.py       37 test agent, guardrail và tools

docs/
  pitch_and_legal.md  trả lời 3 câu hỏi pitch + phân tích pháp lý VN

deck/
  hui-onchain.pptx    slide 13 trang
  hui-onchain.pdf     bản PDF cùng nội dung
  build.js            script pptxgenjs để tái tạo deck
```

---

## Yêu cầu môi trường

| Công cụ | Phiên bản | Dùng để |
|---------|-----------|---------|
| Foundry (`forge`, `cast`) | nightly | build + test Solidity |
| Node.js | ≥18 | build deck (tuỳ chọn) |
| Python | ≥3.10 | sim, app, ai |
| pip packages | xem bên dưới | — |

```bash
pip install web3 streamlit eth-abi eth-utils requests
```

---

## Chạy test Python (không cần network)

```bash
cd hui-onchain
python3 -m unittest sim.test_contract_port sim.test_fuzz app.test_logic ai.test_agent
```

---

## Chạy test Foundry

```bash
# Cài Foundry nếu chưa có:
curl -L https://foundry.paradigm.xyz | bash && foundryup

cd hui-onchain/contracts
forge install foundry-rs/forge-std --no-git   # cài dependency
forge test -vv
```

---

## Deploy lên Fuji (Avalanche testnet)

**1. Lấy AVAX testnet**  
Faucet: https://faucet.avax.network/ — chọn Fuji, dán địa chỉ ví.

**2. Set biến môi trường**

```bash
export PRIVATE_KEY=0x<khóa-riêng-ví-test>
export FUJI_RPC=https://api.avax-test.network/ext/bc/C/rpc
export MOCK_USDC=     # để trống nếu muốn deploy MockUSDC mới
```

**3. Deploy MockUSDC (nếu cần)**

```bash
cd hui-onchain/contracts
forge script script/Deploy.s.sol:DeployMockUSDC \
  --rpc-url $FUJI_RPC \
  --broadcast \
  --private-key $PRIVATE_KEY
# Lưu địa chỉ MockUSDC in ra
export MOCK_USDC=<địa-chỉ-vừa-in>
```

**4. Deploy RoscaFactory**

```bash
forge script script/Deploy.s.sol:DeployFactory \
  --rpc-url $FUJI_RPC \
  --broadcast \
  --private-key $PRIVATE_KEY \
  --sig "run(address,address,uint16)" $MOCK_USDC $WALLET_ADDRESS 50
# 50 bps = 0.5% phí nền tảng
```

**5. Tạo dây hụi mẫu (4 người, 1 kỳ 5 phút để demo)**

```bash
forge script script/Deploy.s.sol:CreateSampleCircle \
  --rpc-url $FUJI_RPC \
  --broadcast \
  --private-key $PRIVATE_KEY \
  --sig "run(address)" <FACTORY_ADDRESS>
```

**6. Chạy Streamlit**

```bash
cd hui-onchain
export FACTORY_ADDRESS=<địa-chỉ-factory>
export USDC_ADDRESS=$MOCK_USDC
streamlit run app/main.py
```

---

## Tóm tắt thiết kế quan trọng

### Tại sao hụi chết trả `A` chứ không phải `A + d`?

Nếu hụi chết trả `A + d`, mỗi kỳ hợp đồng thu được nhiều hơn số nó phát ra —
tức là **tự sinh tiền**. Trên blockchain đó là điều không thể. Quy tắc đúng:

- Người thắng đấu giá (cần tiền sớm): nhận pot, kỳ này không đóng
- Người chưa nhận (hụi sống): đóng `A − d` (giảm bởi bid thắng)
- Người đã nhận (hụi chết): đóng `A` (không thêm d)

`pot = (n−1)·(A−d) + (số người đã nhận)·d`  
Tổng lãi/lỗ của mọi thành viên cộng lại = 0 mỗi kỳ.

### Trần lãi 20%/năm (Điều 468 BLDS 2015)

```solidity
function maxBid() public view returns (uint256) {
    return (contribution * 2000 * period) / (10_000 * 365 days);
}
```

Bid vượt trần → `revert BidAboveCap`. Contract không tự cắt xuống mà để giao dịch thất bại — người dùng biết lý do.

### Ba quỹ tách biệt

| Quỹ | Mục đích |
|-----|----------|
| `depositsHeld` | ký quỹ hoàn lại sau khi kết thúc |
| `penaltyPool` | phí trễ 2% + deposit bị slashed |
| `potInFlight` | tiền đang gom trong kỳ hiện tại |

Bất biến: `balanceOf(contract) == depositsHeld + penaltyPool + potInFlight`  
Sau khi đóng dây: ba quỹ đều = 0.

---

## Giới hạn pháp lý (phải nói khi demo)

1. Smart contract chưa được Nghị định 19/2019/NĐ-CP công nhận thay thế văn bản có chữ ký
2. USDC ≠ VND — dây hụi bằng ngoại tệ là vùng xám pháp lý
3. Dây ≥ 100 triệu đồng phải khai báo UBND cấp xã; contract không tự làm hộ
4. Không có cơ chế can thiệp khi contract sai — vừa là ưu điểm, vừa là rủi ro

Trước khi dùng USDC thật: cần audit độc lập và tư vấn pháp lý.

---

## Liên hệ nhóm

Nhóm 2–3 người · Avalanche Builder House 2026
