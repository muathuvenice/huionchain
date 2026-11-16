const pptxgen = require("pptxgenjs");
const fs = require("fs");

const THEME = {
  name: "Hui On-Chain",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "16202E", lt1: "FFFFFF", dk2: "3A4553", lt2: "F4F1EA",
    accent1: "C0503A", accent2: "1F6F63", accent3: "D9A521",
    accent4: "6B7A8F", accent5: "8C3B2E", accent6: "BFC7D1",
    hlink: "1F6F63", folHlink: "8C3B2E",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";   // 13.3 x 7.5
pres.author = "Team Hui On-Chain";
pres.company = "Avalanche Builder House";
pres.title = "Hui On-Chain";

const W = 13.333, H = 7.5, M = 0.75;
const C = { ink: "16202E", paper: "FFFFFF", cream: "F4F1EA",
            clay: "C0503A", teal: "1F6F63", gold: "D9A521", grey: "6B7A8F" };

// ── layouts ───────────────────────────────────────────────────────
pres.defineSlideMaster({
  title: "TITLE",
  background: { color: C.ink },
  objects: [],
});
pres.defineSlideMaster({
  title: "LIGHT",
  background: { color: C.paper },
  objects: [],
});
pres.defineSlideMaster({
  title: "CREAM",
  background: { color: C.cream },
  objects: [],
});
pres.defineSlideMaster({
  title: "DARK",
  background: { color: C.ink },
  objects: [],
});

// helpers
const tx = (s, t, o = {}) => s.addText(t, {
  isTextBox: true, fontFace: "Calibri", color: C.ink, ...o });

function slideTitle(s, t, opts = {}) {
  tx(s, t, { x: M, y: 0.55, w: W - 2 * M, h: 0.75,
    fontSize: 34, bold: true, fontFace: "Cambria",
    color: opts.color || C.ink, margin: 0, valign: "middle" });
}

function kicker(s, t, opts = {}) {
  tx(s, t, { x: M, y: 0.28, w: W - 2 * M, h: 0.3,
    fontSize: 11, bold: true, color: opts.color || C.clay,
    charSpacing: 2, margin: 0, valign: "middle" });
}

function footer(s, n, dark) {
  tx(s, "Hụi On-Chain · Avalanche Builder House", {
    x: M, y: H - 0.45, w: 6, h: 0.25, fontSize: 9,
    color: dark ? "8B95A5" : C.grey, margin: 0, valign: "middle" });
  tx(s, String(n), {
    x: W - M - 0.6, y: H - 0.45, w: 0.6, h: 0.25, fontSize: 9,
    color: dark ? "8B95A5" : C.grey, align: "right", margin: 0, valign: "middle" });
}

// ══════════════════════════════════════════════════════ 1. cover
{
  const s = pres.addSlide({ masterName: "TITLE" });

  // Vòng tròn hụi — motif: các vòng lồng nhau
  const cx = 10.1, cy = 3.75;
  [2.45, 1.75, 1.05].forEach((r, i) => {
    s.addShape(pres.ShapeType.ellipse, {
      x: cx - r, y: cy - r, w: r * 2, h: r * 2,
      fill: { type: "none" },
      line: { color: i === 0 ? C.teal : "2A3A4A", width: i === 0 ? 2.5 : 1.2 },
    });
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: cx - 0.34, y: cy - 0.34, w: 0.68, h: 0.68,
    fill: { color: C.clay }, line: { color: C.clay, width: 0 },
  });
  tx(s, "1", { x: cx - 0.34, y: cy - 0.34, w: 0.68, h: 0.68,
    fontSize: 20, bold: true, color: "FFFFFF", align: "center",
    valign: "middle", margin: 0, fontFace: "Cambria" });

  kicker(s, "AVALANCHE BUILDER HOUSE · 2026", { color: C.gold });
  tx(s, "Hụi On-Chain", {
    x: M, y: 1.9, w: 7.4, h: 1.5,
    fontSize: 54, bold: true, fontFace: "Cambria", color: "FFFFFF",
    margin: 0, valign: "middle" });
  tx(s, "Quỹ nằm trong hợp đồng.\nKhông nằm trong tay chủ hụi.", {
    x: M, y: 3.35, w: 7.0, h: 1.1,
    fontSize: 22, color: "C9D2DE", margin: 0, lineSpacing: 34 });

  tx(s, "ROSCA · USDC · đấu giá kín commit-reveal · trần lãi 20%/năm", {
    x: M, y: 5.35, w: 8.4, h: 0.35, fontSize: 13, color: C.teal,
    margin: 0 });

  tx(s, "Nhóm 2–3 người · Solidity · Foundry · Streamlit · Web3.py", {
    x: M, y: 5.85, w: 8.4, h: 0.35, fontSize: 11, color: "7E8A9B",
    margin: 0 });
}

// ══════════════════════════════════════════════════ 2. vấn đề
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  kicker(s, "VẤN ĐỀ");
  slideTitle(s, "Chủ hụi giữ tiền, người chơi giữ niềm tin");

  const items = [
    ["Bể hụi", "Chủ hụi ôm tiền bỏ trốn sau khi gom xong các kỳ đầu. Người chưa nhận mất trắng."],
    ["Không kiểm chứng được", "Không ai biết quỹ còn bao nhiêu, ai đã đóng, ai chưa. Sổ chỉ chủ hụi có."],
    ["Không có bằng chứng", "Khi tranh chấp, không có bản ghi nào có giá trị. Nghị định 19 yêu cầu văn bản — hụi tự phát thì không có."],
  ];
  items.forEach(([h, d], i) => {
    const y = 1.85 + i * 1.55;
    s.addShape(pres.ShapeType.roundRect, {
      x: M, y, w: W - 2 * M, h: 1.35,
      fill: { color: i === 0 ? "FBEFEC" : C.cream },
      line: { color: i === 0 ? "E8C4BB" : "E4DFD3", width: 1 },
      rectRadius: 0.06,
    });
    tx(s, h, { x: M + 0.3, y: y + 0.16, w: 2.6, h: 0.4,
      fontSize: 16, bold: true, fontFace: "Cambria", color: C.ink, margin: 0 });
    tx(s, d, { x: M + 0.3, y: y + 0.62, w: W - 2 * M - 0.6, h: 0.62,
      fontSize: 13, color: "46505E", margin: 0 });
  });
  footer(s, 2, false);
}

// ══════════════════════════════════════════════════ 3. giải pháp
{
  const s = pres.addSlide({ masterName: "DARK" });
  kicker(s, "GIẢI PHÁP");
  slideTitle(s, "Hợp đồng thay chủ hụi", { color: "FFFFFF" });
  tx(s, "Một dây hụi 10 người, góp 1 triệu/kỳ, 10 kỳ. Mỗi kỳ một người nhận pot. Không ai được rút tiền ngoài quy tắc.", {
    x: M, y: 1.45, w: 11.4, h: 0.5, fontSize: 14, color: "A9B4C4", margin: 0 });

  const cards = [
    ["Góp mỗi kỳ", "A", "Người chưa nhận\nđóng A − d", C.teal],
    ["Hụi chết", "A", "Người đã nhận\nđóng đủ A", C.gold],
    ["Người thắng", "0", "Nhận pot, kỳ này\nkhông phải đóng", C.clay],
  ];
  cards.forEach(([label, big, sub, col], i) => {
    const x = M + i * 3.95;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.35, w: 3.6, h: 2.5,
      fill: { color: "1E2A3A" }, line: { color: "2E3D50", width: 1 },
      rectRadius: 0.06,
    });
    tx(s, label, { x: x + 0.3, y: 2.55, w: 3.0, h: 0.3,
      fontSize: 11, bold: true, color: "8B98AA", charSpacing: 1.5, margin: 0 });
    tx(s, big, { x: x + 0.3, y: 2.85, w: 3.0, h: 0.95,
      fontSize: 44, bold: true, fontFace: "Cambria", color: col, margin: 0 });
    tx(s, sub, { x: x + 0.3, y: 3.85, w: 3.0, h: 0.85,
      fontSize: 12.5, color: "C3CCD9", margin: 0, lineSpacing: 19 });
  });

  tx(s, "pot = (n−1)·(A−d) + (số người đã nhận)·A      →      pot luôn bằng đúng số tiền thu trong kỳ", {
    x: M, y: 5.25, w: 11.6, h: 0.5, fontSize: 14, fontFace: "Consolas",
    color: "FFFFFF", margin: 0 });
  tx(s, "Hệ quả: tổng lãi/lỗ của mọi thành viên cộng lại bằng 0. Hợp đồng không bao giờ tạo ra tiền — đó là điều kiện để nó không bao giờ thiếu tiền để trả.", {
    x: M, y: 5.85, w: 11.6, h: 0.7, fontSize: 13, color: "A9B4C4", margin: 0 });
  footer(s, 3, true);
}

// ══════════════════════════════════════════ 4. ba câu hỏi: on-chain
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  kicker(s, "CÂU HỎI 1");
  slideTitle(s, "Vì sao phải là blockchain?");

  const rows = [
    ["Tiền do mã giữ, không do người giữ",
     "Không có hàm nào cho chủ hụi rút tiền của người khác. Deploy xong là không ai sửa được quy tắc."],
    ["Mọi dòng tiền công khai",
     "Từng kỳ góp, từng pot, từng lần cáo đều là sự kiện on-chain. Ai cũng đọc được, không cần tin ai."],
    ["Không cần tin chủ hụi",
     "Người lạ cùng chơi được vì quy tắc do mã cưỡng chế, không do uy tín cá nhân."],
  ];
  rows.forEach(([h, d], i) => {
    const y = 1.75 + i * 1.55;
    s.addShape(pres.ShapeType.ellipse, {
      x: M, y: y + 0.12, w: 0.5, h: 0.5,
      fill: { color: C.teal }, line: { color: C.teal, width: 0 },
    });
    tx(s, String(i + 1), { x: M, y: y + 0.12, w: 0.5, h: 0.5,
      fontSize: 16, bold: true, color: "FFFFFF", align: "center",
      valign: "middle", margin: 0, fontFace: "Cambria" });
    tx(s, h, { x: M + 0.8, y: y + 0.1, w: 10.6, h: 0.4,
      fontSize: 16.5, bold: true, fontFace: "Cambria", color: C.ink, margin: 0 });
    tx(s, d, { x: M + 0.8, y: y + 0.55, w: 10.6, h: 0.6,
      fontSize: 13, color: "46505E", margin: 0 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M, y: 6.3, w: W - 2 * M, h: 0.72,
    fill: { color: C.cream }, line: { color: "E4DFD3", width: 1 }, rectRadius: 0.06,
  });
  tx(s, "Nếu dùng cơ sở dữ liệu tập trung, chỉ là dời vấn đề: vẫn phải tin người quản lý server.", {
    x: M + 0.3, y: 6.3, w: W - 2 * M - 0.6, h: 0.72,
    fontSize: 13.5, italic: true, color: "46505E", margin: 0, valign: "middle" });
  footer(s, 4, false);
}

// ══════════════════════════════════════════ 5. ba câu hỏi: avalanche
{
  const s = pres.addSlide({ masterName: "CREAM" });
  kicker(s, "CÂU HỎI 2");
  slideTitle(s, "Vì sao chọn Avalanche?");

  const stats = [
    ["< 1 USD", "phí cho cả dây hụi 10 người,\n10 kỳ (≈100 giao dịch)"],
    ["~2 giây", "thời gian hoàn tất giao dịch,\nkhông phải chờ 30 giây"],
    ["Native USDC", "Circle phát hành trực tiếp trên\nC-Chain, không qua bridge"],
  ];
  stats.forEach(([big, sub], i) => {
    const x = M + i * 3.85;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 1.8, w: 3.5, h: 1.95,
      fill: { color: "FFFFFF" }, line: { color: "E0DACC", width: 1 }, rectRadius: 0.06,
    });
    tx(s, big, { x: x + 0.25, y: 2.0, w: 3.0, h: 0.75,
      fontSize: 32, bold: true, fontFace: "Cambria", color: C.clay, margin: 0 });
    tx(s, sub, { x: x + 0.25, y: 2.75, w: 3.0, h: 0.85,
      fontSize: 11.5, color: "46505E", margin: 0, lineSpacing: 16 });
  });

  tx(s, "Vì sao phí quan trọng hơn nó có vẻ", {
    x: M, y: 4.15, w: 8, h: 0.4,
    fontSize: 16, bold: true, fontFace: "Cambria", color: C.ink, margin: 0 });

  // thanh so sánh phí
  const bars = [["Avalanche C-Chain", 0.06, C.teal],
                ["Ethereum mainnet", 1.0, C.clay]];
  bars.forEach(([label, frac, col], i) => {
    const y = 4.75 + i * 0.85;
    tx(s, label, { x: M, y, w: 2.6, h: 0.34,
      fontSize: 12, color: C.ink, margin: 0, valign: "middle" });
    s.addShape(pres.ShapeType.rect, {
      x: M + 2.7, y: y + 0.03, w: 6.6, h: 0.28,
      fill: { color: "E8E3D7" }, line: { color: "E8E3D7", width: 0 },
    });
    s.addShape(pres.ShapeType.rect, {
      x: M + 2.7, y: y + 0.03, w: Math.max(0.12, 6.6 * frac), h: 0.28,
      fill: { color: col }, line: { color: col, width: 0 },
    });
  });
  tx(s, "Chi phí tương đối cho ~100 giao dịch. Với nhóm tiết kiệm nhỏ, đây là điều kiện sống còn, không phải chi tiết kỹ thuật.", {
    x: M, y: 6.45, w: 11.2, h: 0.45, fontSize: 11.5, italic: true,
    color: C.grey, margin: 0 });
  footer(s, 5, false);
}

// ═════════════════════════════════════ 6. ba câu hỏi: tiền từ đâu
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  kicker(s, "CÂU HỎI 3");
  slideTitle(s, "Tiền lãi đến từ đâu — và không đến từ đâu");

  s.addShape(pres.ShapeType.roundRect, {
    x: M, y: 1.7, w: 5.85, h: 4.3,
    fill: { color: "EDF5F3" }, line: { color: "BFDDD7", width: 1 }, rectRadius: 0.06,
  });
  tx(s, "NGUỒN 1 · TRONG HỢP ĐỒNG", {
    x: M + 0.35, y: 1.9, w: 5.2, h: 0.3, fontSize: 11, bold: true,
    color: C.teal, charSpacing: 1.5, margin: 0 });
  tx(s, "Lãi đấu giá", { x: M + 0.35, y: 2.2, w: 5.2, h: 0.55,
    fontSize: 25, bold: true, fontFace: "Cambria", color: C.ink, margin: 0 });
  tx(s, "Người cần tiền sớm kêu giá, tức chấp nhận nhận pot bị chiết khấu. Khoản chiết khấu đó không biến mất — nó thành phần giảm trừ cho người nhận muộn.", {
    x: M + 0.35, y: 2.85, w: 5.2, h: 1.25, fontSize: 12.5, color: "3E4B5A",
    margin: 0, lineSpacing: 19 });
  tx(s, "Người nhận sớm: lỗ\nNgười nhận muộn: lời\nTổng cộng: bằng 0", {
    x: M + 0.35, y: 4.2, w: 5.2, h: 1.05, fontSize: 12.5, bold: true,
    color: C.teal, margin: 0, lineSpacing: 21 });
  tx(s, "Đây là phân bổ lại trong nhóm, không phải lãi từ bên ngoài rót vào.", {
    x: M + 0.35, y: 5.35, w: 5.2, h: 0.55, fontSize: 10.5, italic: true,
    color: C.grey, margin: 0 });

  s.addShape(pres.ShapeType.roundRect, {
    x: M + 6.25, y: 1.7, w: 5.85, h: 4.3,
    fill: { color: "FBF6E8" }, line: { color: "E8DCB8", width: 1 }, rectRadius: 0.06,
  });
  tx(s, "NGUỒN 2 · NGOÀI HỢP ĐỒNG", {
    x: M + 6.6, y: 1.9, w: 5.2, h: 0.3, fontSize: 11, bold: true,
    color: "9A7414", charSpacing: 1.5, margin: 0 });
  tx(s, "Yield trên tiền nhàn rỗi", { x: M + 6.6, y: 2.2, w: 5.2, h: 0.55,
    fontSize: 25, bold: true, fontFace: "Cambria", color: C.ink, margin: 0 });
  tx(s, "Giữa các kỳ, tiền chưa phân phối có thể gửi vào lending protocol trên Avalanche để sinh lời.", {
    x: M + 6.6, y: 2.85, w: 5.2, h: 0.9, fontSize: 12.5, color: "3E4B5A",
    margin: 0, lineSpacing: 19 });
  tx(s, "DefiLlama API\n→ dashboard gợi ý top 3 pool\n→ người dùng bấm nút\n→ tiền mới được đẩy đi", {
    x: M + 6.6, y: 3.95, w: 5.2, h: 1.15, fontSize: 12.5, bold: true,
    color: "9A7414", margin: 0, lineSpacing: 21 });
  tx(s, "HITL: quyết định đầu tư không tự động. Hợp đồng không tự chuyển tiền đi.", {
    x: M + 6.6, y: 5.2, w: 5.2, h: 0.6, fontSize: 10.5, italic: true,
    color: C.grey, margin: 0 });

  tx(s, "Điều không được nói khi pitch: không có nguồn thứ ba. Hụi không sinh lãi từ ngoài thị trường — nếu ai đó hứa lãi cao hơn trần 20%/năm, đó là dấu hiệu bể hụi.", {
    x: M, y: 6.18, w: 11.9, h: 0.6, fontSize: 11.5, bold: true,
    color: C.clay, margin: 0 });
  footer(s, 6, false);
}

// ═══════════════════════════════════════════ 7. đấu giá kín
{
  const s = pres.addSlide({ masterName: "DARK" });
  kicker(s, "CƠ CHẾ", { color: C.gold });
  slideTitle(s, "Đấu giá kín: không ai thấy giá của ai", { color: "FFFFFF" });

  const steps = [
    ["1", "Cam kết", "keccak256(bid, salt, ví, vòng)\nKhông lộ giá. Giá nằm trong hash."],
    ["2", "Chờ hết hạn", "Không ai reveal trước hạn —\ncontract revert nếu thử sớm."],
    ["3", "Mở giá", "revealBid(bid, salt). Sai salt → revert.\nVượt trần 20% → revert."],
    ["4", "Chốt", "Giá thấp nhất thắng.\nCommit mà không reveal → mất nửa ký quỹ."],
  ];
  steps.forEach(([n, h, d], i) => {
    const x = M + i * 2.95;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.05, w: 2.65, h: 2.9,
      fill: { color: "1E2A3A" }, line: { color: i === 1 ? C.gold : "2E3D50", width: 1 },
      rectRadius: 0.06,
    });
    tx(s, n, { x: x + 0.25, y: 2.2, w: 0.5, h: 0.5, fontSize: 22, bold: true,
      fontFace: "Cambria", color: i === 1 ? C.gold : C.teal, margin: 0 });
    tx(s, h, { x: x + 0.25, y: 2.7, w: 2.2, h: 0.4, fontSize: 14.5, bold: true,
      fontFace: "Cambria", color: "FFFFFF", margin: 0 });
    tx(s, d, { x: x + 0.25, y: 3.15, w: 2.15, h: 1.6, fontSize: 10.5,
      color: "A9B4C4", margin: 0, lineSpacing: 15 });
  });

  tx(s, "Vì sao không cho reveal sớm: nếu người sau thấy giá người trước, cuộc đấu giá không còn kín — người cuối luôn thắng bằng cách kêu thấp hơn 1 đơn vị.", {
    x: M, y: 5.3, w: 11.6, h: 0.65, fontSize: 13, color: "C3CCD9", margin: 0 });
  tx(s, "Đây là lý do phải khoá reveal theo thời gian, không chỉ dựa vào thiện chí.", {
    x: M, y: 6.0, w: 11.6, h: 0.4, fontSize: 12, italic: true, color: "7E8A9B", margin: 0 });
  footer(s, 7, true);
}

// ══════════════════════════════════════════ 8. trần lãi 20%
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  kicker(s, "PHÁP LÝ · ĐIỀU 468 BLDS 2015");
  slideTitle(s, "Trần 20%/năm được cưỡng chế trong code");

  s.addShape(pres.ShapeType.roundRect, {
    x: M, y: 1.7, w: 11.85, h: 1.15,
    fill: { color: C.cream }, line: { color: "E4DFD3", width: 1 }, rectRadius: 0.06,
  });
  tx(s, "d ≤ A × 20% × period / YEAR", {
    x: M + 0.4, y: 1.7, w: 8, h: 1.15, fontSize: 24,
    fontFace: "Consolas", color: C.ink, margin: 0, valign: "middle" });
  tx(s, "maxBid() trong RoscaCircle.sol", {
    x: M + 8.2, y: 1.7, w: 3.2, h: 1.15, fontSize: 11,
    fontFace: "Consolas", color: C.grey, align: "right",
    margin: 0, valign: "middle" });

  // bảng ví dụ
  const rows = [
    ["Kỳ hạn", "Mức góp", "Trần giá kêu", "APR tương đương"],
    ["7 ngày", "1.000.000", "3.835", "20,0%"],
    ["30 ngày", "1.000.000", "16.438", "20,0%"],
    ["30 ngày", "10.000.000", "164.383", "20,0%"],
  ];
  s.addTable(rows.map((r, i) => r.map((c, j) => ({
    text: c,
    options: {
      fontSize: i === 0 ? 11 : 12.5,
      bold: i === 0 || j === 3,
      color: i === 0 ? "FFFFFF" : C.ink,
      fill: { color: i === 0 ? C.ink : (i % 2 ? "FFFFFF" : C.cream) },
      fontFace: i === 0 ? "Calibri" : (j === 3 ? "Consolas" : "Calibri"),
      align: j === 0 ? "left" : "right",
    },
  }))), {
    x: M, y: 3.15, w: 8.2, colW: [2.0, 2.1, 2.1, 2.0],
    border: { type: "solid", color: "E4DFD3", pt: 1 },
    rowH: 0.42, valign: "middle", margin: 0.1,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M + 8.5, y: 3.15, w: 3.35, h: 2.1,
    fill: { color: "FBEFEC" }, line: { color: "E8C4BB", width: 1 }, rectRadius: 0.06,
  });
  tx(s, "Vượt trần → revert", { x: M + 8.75, y: 3.3, w: 2.9, h: 0.4,
    fontSize: 14, bold: true, fontFace: "Cambria", color: C.clay, margin: 0 });
  tx(s, "Không cắt âm thầm. Không làm tròn xuống. Giao dịch thất bại và người dùng biết vì sao.", {
    x: M + 8.75, y: 3.72, w: 2.9, h: 1.0, fontSize: 11.5,
    color: "5A4038", margin: 0, lineSpacing: 17 });

  tx(s, "Cưỡng chế trong code khác với ghi trong điều khoản: điều khoản có thể bị bỏ qua, contract thì không.", {
    x: M, y: 5.65, w: 11.8, h: 0.5, fontSize: 12.5, italic: true,
    color: C.grey, margin: 0 });
  tx(s, "Đi kèm: ký quỹ 1 kỳ góp/người, phí trễ 2%/kỳ, ghi nhận cáo công khai và chia quỹ phạt cho người không cáo.", {
    x: M, y: 6.15, w: 11.8, h: 0.5, fontSize: 12.5, color: C.ink, margin: 0 });
  footer(s, 8, false);
}

// ══════════════════════════════════════════════ 9. giới hạn pháp lý
{
  const s = pres.addSlide({ masterName: "CREAM" });
  kicker(s, "NÓI THẲNG");
  slideTitle(s, "Bốn giới hạn pháp lý nhóm không giải quyết được");

  const limits = [
    ["Hợp đồng thông minh chưa được luật hụi công nhận",
     "Nghị định 19/2019 yêu cầu văn bản có chữ ký. Toà có thể không công nhận smart contract thay thế."],
    ["USDC chưa phải VND",
     "Quy định hụi viết bằng đồng Việt Nam. Hụi bằng USDC là vùng xám."],
    ["Nghĩa vụ khai báo vẫn thuộc về người dùng",
     "Dây từ 100 triệu đồng phải thông báo UBND cấp xã. Contract không làm hộ được."],
    ["Không có cơ chế sửa khi contract sai",
     "Không ai can thiệp được — vừa là ưu điểm, vừa là rủi ro."],
  ];
  limits.forEach(([h, d], i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M + col * 6.1, y = 1.75 + row * 2.15;
    tx(s, h, { x, y, w: 5.7, h: 0.72, fontSize: 14, bold: true,
      fontFace: "Cambria", color: C.ink, margin: 0, lineSpacing: 19 });
    tx(s, d, { x, y: y + 0.78, w: 5.7, h: 0.95, fontSize: 11.5,
      color: "46505E", margin: 0, lineSpacing: 16 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M, y: 6.05, w: W - 2 * M, h: 0.8,
    fill: { color: "FFFFFF" }, line: { color: "E0DACC", width: 1 }, rectRadius: 0.06,
  });
  tx(s, "Không phải tư vấn pháp lý. Trước khi triển khai thương mại, cần luật sư và cần kiểm tra các nghị định hướng dẫn Luật Công nghiệp Công nghệ số 2025.", {
    x: M + 0.3, y: 6.05, w: W - 2 * M - 0.6, h: 0.8, fontSize: 11.5,
    italic: true, color: C.grey, margin: 0, valign: "middle" });
  footer(s, 9, false);
}

// ══════════════════════════════════════════ 10. credit score
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  kicker(s, "AI · NHƯNG KHÔNG DÙNG LLM ĐỂ CHẤM ĐIỂM");
  slideTitle(s, "Điểm uy tín tính từ dữ liệu on-chain");

  tx(s, "Vì sao không để LLM sinh ra điểm số", {
    x: M, y: 1.6, w: 5.6, h: 0.4, fontSize: 16, bold: true,
    fontFace: "Cambria", color: C.ink, margin: 0 });
  ["Không tái lập được — cùng ví, hai lần hỏi ra hai điểm",
   "Không giải thích được cho người bị từ chối",
   "Không kiểm toán được — không ai chứng minh điểm đúng",
  ].forEach((t, i) => {
    tx(s, "·  " + t, { x: M, y: 2.1 + i * 0.62, w: 5.7, h: 0.55,
      fontSize: 12, color: "46505E", margin: 0, lineSpacing: 17 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M, y: 4.15, w: 5.7, h: 2.05,
    fill: { color: "EDF5F3" }, line: { color: "BFDDD7", width: 1 }, rectRadius: 0.06,
  });
  tx(s, "Điểm ví mới = 500, không phải 0", {
    x: M + 0.3, y: 4.3, w: 5.1, h: 0.4, fontSize: 13.5, bold: true,
    fontFace: "Cambria", color: C.teal, margin: 0 });
  tx(s, "Ví chưa có lịch sử không bị phạt vì thiếu dữ liệu — chỉ những thành phần có dữ liệu mới được tính. Đây chính là cách giải bài toán cold start mà dự án đặt ra.", {
    x: M + 0.3, y: 4.72, w: 5.1, h: 1.3, fontSize: 11.5, color: "3E4B5A",
    margin: 0, lineSpacing: 17 });

  // bảng trọng số
  tx(s, "Trọng số", { x: M + 6.2, y: 1.6, w: 5.3, h: 0.4,
    fontSize: 16, bold: true, fontFace: "Cambria", color: C.ink, margin: 0 });
  const w = [["Trả đúng hạn", 0.45, C.teal], ["Hoàn thành dây", 0.20, C.teal],
             ["Kinh nghiệm", 0.15, C.gold], ["Hành vi đấu giá", 0.10, C.gold],
             ["Tuổi ví", 0.10, C.grey]];
  w.forEach(([label, frac, col], i) => {
    const y = 2.12 + i * 0.55;
    tx(s, label, { x: M + 6.2, y, w: 2.2, h: 0.3, fontSize: 11.5,
      color: C.ink, margin: 0, valign: "middle" });
    s.addShape(pres.ShapeType.rect, {
      x: M + 8.45, y: y + 0.06, w: 2.3, h: 0.2,
      fill: { color: "EAE6DC" }, line: { color: "EAE6DC", width: 0 } });
    s.addShape(pres.ShapeType.rect, {
      x: M + 8.45, y: y + 0.06, w: Math.max(0.1, 2.3 * frac / 0.45), h: 0.2,
      fill: { color: col }, line: { color: col, width: 0 } });
    tx(s, `${Math.round(frac * 100)}%`, { x: M + 10.85, y, w: 0.6, h: 0.3,
      fontSize: 11, color: C.grey, align: "right", margin: 0, valign: "middle" });
  });

  tx(s, "Cáo (default) trừ thẳng tới 450 điểm — một lần bùng nợ nói nhiều hơn hai mươi kỳ trả đúng hẹn.", {
    x: M + 6.2, y: 5.0, w: 5.3, h: 0.75, fontSize: 12, bold: true,
    color: C.clay, margin: 0, lineSpacing: 17 });
  tx(s, "Điểm chỉ để gợi ý. Contract không chặn ai dựa trên điểm — chấm sai không được phép tước quyền tự quyết của người dùng.", {
    x: M + 6.2, y: 5.8, w: 5.3, h: 0.6, fontSize: 10.5, italic: true,
    color: C.grey, margin: 0 });
  footer(s, 10, false);
}

// ══════════════════════════════════════════ 11. kiến trúc
{
  const s = pres.addSlide({ masterName: "CREAM" });
  kicker(s, "KIẾN TRÚC");
  slideTitle(s, "Ba tầng, hai người làm được trong 18 ngày");

  const tiers = [
    ["On-chain", "RoscaFactory + RoscaCircle", "Solidity 0.8.24 · Foundry · Fuji C-Chain", C.clay],
    ["Off-chain", "Chấm điểm + đọc log", "Python · Web3.py · DefiLlama API", C.teal],
    ["Giao diện", "Streamlit", "Tạo dây · đóng hụi · đấu giá · lịch sử", C.gold],
  ];
  tiers.forEach(([k, h, d, col], i) => {
    const y = 1.85 + i * 1.5;
    s.addShape(pres.ShapeType.roundRect, {
      x: M, y, w: 8.4, h: 1.25,
      fill: { color: "FFFFFF" }, line: { color: "E0DACC", width: 1 }, rectRadius: 0.06,
    });
    tx(s, k, { x: M + 0.3, y: y + 0.15, w: 1.6, h: 0.3, fontSize: 10,
      bold: true, color: col, charSpacing: 1.2, margin: 0 });
    tx(s, h, { x: M + 0.3, y: y + 0.45, w: 7.7, h: 0.4, fontSize: 15,
      bold: true, fontFace: "Cambria", color: C.ink, margin: 0 });
    tx(s, d, { x: M + 0.3, y: y + 0.82, w: 7.7, h: 0.32, fontSize: 11,
      color: C.grey, margin: 0 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M + 8.9, y: 1.85, w: 2.95, h: 4.15,
    fill: { color: C.ink }, line: { color: C.ink, width: 0 }, rectRadius: 0.06,
  });
  tx(s, "Bất biến", { x: M + 9.15, y: 2.0, w: 2.5, h: 0.35,
    fontSize: 13, bold: true, fontFace: "Cambria", color: C.gold, margin: 0 });
  tx(s, "balanceOf(contract)\n= ký quỹ\n+ quỹ phạt\n+ pot đang gom", {
    x: M + 9.15, y: 2.42, w: 2.5, h: 1.5, fontSize: 11.5,
    fontFace: "Consolas", color: "C3CCD9", margin: 0, lineSpacing: 19 });
  tx(s, "Đóng hụi xong\n→ về đúng 0", {
    x: M + 9.15, y: 4.15, w: 2.5, h: 0.9, fontSize: 12, bold: true,
    color: "FFFFFF", margin: 0, lineSpacing: 18 });
  tx(s, "Kiểm chứng bằng 400 kịch bản fuzz.", {
    x: M + 9.15, y: 5.15, w: 2.5, h: 0.7, fontSize: 10, italic: true,
    color: "8B98AA", margin: 0 });
  footer(s, 11, false);
}

// ══════════════════════════════════════════ 12. độ tin cậy
{
  const s = pres.addSlide({ masterName: "DARK" });
  kicker(s, "ĐÃ KIỂM CHỨNG", { color: C.gold });
  slideTitle(s, "Không phải demo trông có vẻ chạy", { color: "FFFFFF" });

  const stats = [
    ["15", "kịch bản test\nluồng đầy đủ"],
    ["400", "dây hụi fuzz\nvới giá + cáo ngẫu nhiên"],
    ["15/15", "đột biến cố tình gài\nđều bị test bắt"],
  ];
  stats.forEach(([n, d], i) => {
    const x = M + i * 3.9;
    tx(s, n, { x, y: 1.85, w: 3.5, h: 1.05, fontSize: 50, bold: true,
      fontFace: "Cambria", color: i === 2 ? C.gold : C.teal, margin: 0 });
    tx(s, d, { x, y: 2.9, w: 3.5, h: 1.0, fontSize: 12, color: "A9B4C4",
      margin: 0, lineSpacing: 18 });
  });

  tx(s, "Những lỗi đã tìm ra và sửa trong quá trình làm", {
    x: M, y: 4.15, w: 11.6, h: 0.4, fontSize: 14, bold: true,
    fontFace: "Cambria", color: "FFFFFF", margin: 0 });
  const finds = [
    "Hụi chết đóng A+d làm contract tự sinh tiền — phát hiện qua bất biến pot ≤ (n−1)·A",
    "Người thắng vòng gọi payIn chiếm slot, trả pot khi còn người chưa đóng",
    "Điểm ví mới ra 385 thay vì 500 — công thức chuẩn hoá sai, đã sửa",
  ];
  finds.forEach((t, i) => {
    tx(s, "→   " + t, { x: M, y: 4.65 + i * 0.62, w: 11.6, h: 0.55,
      fontSize: 12, color: "C3CCD9", margin: 0, lineSpacing: 16 });
  });
  footer(s, 12, true);
}

// ══════════════════════════════════════════ 13. closing
{
  const s = pres.addSlide({ masterName: "TITLE" });

  const cx = 10.55, cy = 3.9;
  [2.2, 1.55, 0.92].forEach((r, i) => {
    s.addShape(pres.ShapeType.ellipse, {
      x: cx - r, y: cy - r, w: r * 2, h: r * 2,
      fill: { type: "none" },
      line: { color: i === 2 ? C.clay : "2A3A4A", width: i === 2 ? 2.5 : 1.2 },
    });
  });

  tx(s, "Hụi không cần thêm niềm tin.\nNó cần bớt một người giữ tiền.", {
    x: M, y: 2.1, w: 7.6, h: 1.9, fontSize: 30, bold: true,
    fontFace: "Cambria", color: "FFFFFF", margin: 0, lineSpacing: 46 });

  tx(s, "Việc cần làm tiếp", { x: M, y: 4.35, w: 6, h: 0.35,
    fontSize: 11, bold: true, color: C.gold, charSpacing: 1.5, margin: 0 });
  ["Deploy lên Fuji và chạy một dây thật với 4 ví",
   "Kiểm tra nghị định hướng dẫn Luật Công nghiệp Công nghệ số 2025",
   "Thuê audit trước khi dùng USDC thật",
  ].forEach((t, i) => {
    tx(s, "·  " + t, { x: M, y: 4.8 + i * 0.42, w: 7.5, h: 0.4,
      fontSize: 12.5, color: "C3CCD9", margin: 0 });
  });
}

// ── write ──────────────────────────────────────────────────────────
pres.writeFile({ fileName: "hui-onchain.pptx" }).then(async () => {
  const { applyTheme } = require("/sessions/cool-gallant-pascal/mnt/.claude/skills/pptx/scripts/apply_theme.js");
  await applyTheme("hui-onchain.pptx", THEME);
  console.log("done");
});
