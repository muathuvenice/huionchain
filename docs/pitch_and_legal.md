# Hụi On-Chain — Pitch Pack + Phân tích pháp lý

---

## Ba câu hỏi bắt buộc

### 1. Vì sao phải dùng blockchain?

Hụi truyền thống sập vì một lý do đơn giản: **chủ hụi nắm tiền**. Người chơi không có cách nào kiểm tra số dư, không có cách nào ngăn chủ ôm tiền bỏ trốn, và khi xảy ra tranh chấp, không có bằng chứng nào có giá trị pháp lý.

Blockchain giải quyết đúng ba điểm này cùng lúc:

Thứ nhất, **hợp đồng thông minh nắm tiền, không phải con người**. `RoscaCircle.sol` không có hàm nào cho phép chủ hụi rút tiền của người khác. Mọi luồng tiền đều theo quy tắc được cứng hoá trong code, và code đã được deploy thì không ai sửa được.

Thứ hai, **tất cả dòng tiền đều công khai và tái lập được**. Mọi kỳ góp, mọi pot nhận được, mọi lần cáo đều là sự kiện on-chain, ai cũng đọc được từ explorer. Không có "sổ chủ hụi" mà chỉ chủ hụi mới thấy.

Thứ ba, **không cần tin tưởng bất kỳ ai**. Người chơi xa lạ hoàn toàn có thể cùng chơi vì quy tắc được cưỡng chế bởi mã, không phải bởi uy tín cá nhân.

Nếu dùng cơ sở dữ liệu tập trung thay vì blockchain, bạn chỉ dời vấn đề: vẫn phải tin tưởng người quản lý server. Blockchain loại bỏ điểm tin tưởng đó.

### 2. Vì sao chọn Avalanche?

Ba lý do có số liệu, không phải khẩu hiệu:

**Phí thấp**. Một dây hụi 10 người đóng hàng tuần sẽ tạo ra khoảng 100 giao dịch trong 10 tuần. Trên Ethereum mainnet, 100 giao dịch có thể tốn hàng trăm đô phí gas tuỳ trạng thái mạng. Trên Avalanche C-Chain, con số tương tự dưới 1 đô. Với nhóm tiết kiệm nhỏ ở Việt Nam, mức phí đó quyết định dự án có dùng được không.

**Thời gian hoàn tất giao dịch**. Avalanche xác nhận trong vài giây, không phải vài phút. Điều này quan trọng cho trải nghiệm: người dùng bấm "đóng hụi", chờ 2-3 giây thấy xác nhận, không phải chờ 15-30 giây rồi không biết giao dịch đã vào chưa.

**USDC bản địa**. Circle phát hành USDC trực tiếp trên Avalanche C-Chain (không phải wrapped từ chuỗi khác). Điều này loại bỏ rủi ro de-peg từ bridge và đơn giản hoá kế toán. Hụi Việt Nam vốn tính bằng VND; USDC là lớp trung gian ổn định nhất hiện có on-chain.

Lý do thứ tư phù hợp với bối cảnh hackathon: đây là Avalanche Builder House, giám khảo có lý do chính đáng để đánh giá cao các dự án khai thác đúng thế mạnh của C-Chain thay vì chỉ deploy một contract Ethereum lên Avalanche cho có.

### 3. Tiền lãi / yield đến từ đâu?

Có hai nguồn hoàn toàn tách biệt; quan trọng là không lẫn lộn hai nguồn này với nhau khi trình bày.

**Nguồn 1 — lãi đấu giá (nằm trong contract)**. Người cần tiền sớm kêu giá (bidding), tức là chấp nhận nhận ít hơn `n×A`. Khoản chiết khấu đó không biến mất — nó được phân bổ cho những người nhận muộn hơn dưới dạng họ chỉ phải đóng `A - d` thay vì `A`. Hệ thống là zero-sum: tổng lợi nhuận ròng của tất cả thành viên cộng lại bằng 0. Đây không phải lãi từ bên ngoài vào — đây là sự phân bổ lại trong nhóm.

Mức tối đa của `d` bị chặn bởi trần 20%/năm (xem mục pháp lý), được cưỡng chế trong `maxBid()` ngay trong contract.

**Nguồn 2 — yield trên số dư nhàn rỗi (ngoài contract, bonus)**. Giữa các kỳ, tiền trong contract chưa được phân phối. Nếu gửi vào lending protocol như Aave hay Benqi trên Avalanche, phần đó sinh yield. Hiện tại contract có hàm `noteYield()` để ghi nhận yield từ adapter bên ngoài, nhưng không tự đầu tư — đó là quyết định thiết kế có chủ đích (giảm rủi ro, đơn giản hoá audit).

Phần này được tích hợp vào frontend qua DefiLlama API: dashboard hiển thị top 3 pool trên Avalanche theo APY, **gợi ý**, và người dùng hoặc admin **bấm nút** để đẩy tiền đi (HITL — Human in the Loop). Quyết định đầu tư không được tự động hoá.

---

## Phân tích pháp lý Việt Nam

> **Lưu ý**: Phần này là phân tích kỹ thuật pháp lý, không phải tư vấn pháp lý. Nhóm nên tham khảo luật sư trước khi triển khai sản phẩm thương mại.

### Khung pháp lý về hụi

**Nghị định 19/2019/NĐ-CP** (ngày 19/02/2019, hiệu lực 01/04/2019) quy định về hụi, họ, biêu, phường. Đây là văn bản pháp lý chính điều chỉnh hoạt động này.

Các điểm quan trọng nhất với dự án:

**Quy định về hình thức**: Điều 6 Nghị định 19/2019 yêu cầu dây hụi có giá trị từ 100 triệu đồng trở lên phải lập thành văn bản, có chữ ký của tất cả thành viên, và phải được công chứng hoặc chứng thực trong một số trường hợp. Với hụi on-chain, smart contract thay thế văn bản, và chữ ký số (giao dịch blockchain) thay thế chữ ký tay — nhưng hiện tại pháp luật Việt Nam chưa công nhận tường minh sự tương đương này.

**Giới hạn lãi suất**: Bộ luật Dân sự 2015, Điều 468 chặn lãi suất thỏa thuận ở mức 20%/năm (tính trên dư nợ thực tế). Dự án cưỡng chế giới hạn này ngay trong hàm `maxBid()`:

```
d ≤ A × 20% × period / YEAR
```

Tức là `maxBid() = contribution × 2000 × period / (10_000 × YEAR)`. Mọi giá kêu vượt trần bị `revert` ngay tại contract, không để người dùng vô tình vi phạm pháp luật.

**Quy định về khai báo**: Theo Điều 14 Nghị định 19/2019, dây hụi từ 100 triệu đồng trở lên phải được thông báo với UBND cấp xã nơi chủ hụi cư trú. Phần này contract không can thiệp được — đây là nghĩa vụ pháp lý của người dùng.

### Khung pháp lý về tài sản số

**Luật Công nghiệp Công nghệ số 2025** (Quốc hội thông qua giữa 2025, một số điều khoản hiệu lực từ 01/01/2026) lần đầu tiên đưa tài sản mã hoá vào khuôn khổ pháp lý ở Việt Nam.

Các điểm quan trọng:

**USDC trong dự án này không phải tiền tệ**. Nghị định 80/2016/NĐ-CP cấm sử dụng tiền ảo làm phương tiện thanh toán. USDC được dùng trong dự án như một đơn vị giá trị trong hợp đồng, không phải để "thanh toán" theo nghĩa của Luật Ngân hàng. Ranh giới này mỏng và cần được tư vấn pháp lý làm rõ.

**Sandbox và cơ chế thí điểm**. Luật 2025 có quy định về cơ chế sandbox cho sàn giao dịch tài sản mã hoá. Tuy nhiên, dự án hụi on-chain không phải sàn giao dịch nên chưa rõ có cần đăng ký vào sandbox không.

**Điều cần kiểm chứng lại trước khi pitch**: Các văn bản hướng dẫn thi hành Luật 2025 (Nghị định, Thông tư) có thể đã được ban hành sau tháng 11/2026. Nhóm nên kiểm tra trên Cổng thông tin văn bản pháp luật của Chính phủ (vanban.chinhphu.vn) và Bộ Tài chính trước khi trình bày với giám khảo.

### Giới hạn pháp lý rõ ràng của dự án

Nhóm nên trình bày thẳng những giới hạn sau thay vì cố né tránh — giám khảo sẽ hỏi, và trả lời thẳng thắn thì thuyết phục hơn:

Thứ nhất, **hợp đồng thông minh chưa được công nhận tường minh trong luật hụi Việt Nam**. Nếu xảy ra tranh chấp, toà án có thể không công nhận smart contract thay thế hợp đồng văn bản theo Nghị định 19/2019.

Thứ hai, **USDC chưa phải đồng VND**. Quy định về hụi viết bằng VND; hụi bằng USDC là vùng pháp lý xám.

Thứ ba, **Nghị định 19/2019 yêu cầu khai báo**. Dự án không tự động thực hiện nghĩa vụ này — người dùng phải tự làm.

Thứ tư, **không có cơ chế giải quyết tranh chấp off-chain**. Nếu có lỗi kỹ thuật trong contract, không có cơ quan nào can thiệp được — đây vừa là ưu điểm (không ai kiểm soát) vừa là rủi ro (không ai sửa được).

---

## Kịch bản demo (5 phút)

Bước 1: Chủ hụi kết nối ví Core/MetaMask, chọn "Tạo dây hụi mới": 4 người, góp 10 USDC/kỳ, 7 ngày/kỳ, chế độ đấu giá kín.

Bước 2: 3 người khác dùng link mời, kết nối ví, bấm "Tham gia". Mỗi người gửi ký quỹ 10 USDC, MetaMask hiện popup, ký xác nhận.

Bước 3: Vòng 1 bắt đầu. Hai người bấm "Cam kết giá", nhập giá kêu và chuỗi bí mật. Hệ thống tính `keccak256(bid, salt, address, round)` và gửi lên chain. Giá không ai thấy cho đến khi reveal.

Bước 4: Hết hạn commit, hai người bấm "Mở giá". AI credit score phân tích lịch sử ví và hiển thị điểm uy tín của từng người.

Bước 5: Người kêu giá thấp hơn thắng, nhận pot (30 USDC). Dashboard cập nhật trạng thái từng thành viên theo thời gian thực.

> Nếu mạng Fuji không ổn định lúc demo: có video dự phòng quay sẵn trên mạng hoạt động. Đây là rủi ro kỹ thuật đã biết và có kế hoạch dự phòng.

---

## KPI theo sprint plan của nhóm

Sprint 1 (ngày 1–5): Contract Solidity viết và test cơ bản trên Foundry. Kịch bản 4 người chạy được.

Sprint 2 (ngày 6–12): Tích hợp Web3.py, giao diện Streamlit kết nối contract, module credit score chạy được.

Sprint 3 (ngày 13–18): Full system test, video demo, slide pitch. Contract không có lỗi bảo mật cơ bản (reentrancy, integer overflow, access control). AI trả kết quả dưới 30 giây/ví.
