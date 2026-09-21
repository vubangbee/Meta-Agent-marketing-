// Áp bộ lọc: N thẻ tag (logic HOẶC) + khoảng ngày theo THỜI GIAN TẠO.
// Chạy 3 bước riêng biệt và KIỂM TRA kết quả từng bước - không gộp mù thành một lần chạy,
// vì mỗi bước đều có mặc định khác nhau tuỳ fanpage/phiên làm việc.

// ============================================================
// BƯỚC 1 - Tick thẻ tag (LUÔN dò lại index, không hardcode)
// ============================================================
async (page) => {
  const TARGET_TAGS = ['QM','A','B','C','LIÊN LẠC KHÁC','Remarketing','Đã pt','Đã lên tv','Hẹn lịch','Tiềm năng'];

  await page.getByRole('button', { name: 'Lọc theo' }).click();
  await page.waitForTimeout(500);

  // Index checkbox KHÔNG ổn định giữa các trang và các phiên (đã đo lệch 2 lần).
  // Dựng map tên -> index tại chỗ: leo lên tối đa 4 cấp DOM lấy innerText khác rỗng đầu tiên.
  const checkboxes = page.locator('input[type="checkbox"]');
  const total = await checkboxes.count();
  const all = [];
  for (let i = 0; i < total; i++) {
    const text = await checkboxes.nth(i).evaluate(el => {
      let node = el.closest('label') || el.parentElement;
      for (let hop = 0; hop < 4 && node; hop++) {
        const t = node.innerText?.trim();
        if (t) return t;
        node = node.parentElement;
      }
      return '';
    });
    all.push({ i, text: text.slice(0, 40) });
  }

  const map = {};
  for (const tag of TARGET_TAGS) {
    const hit = all.find(x => x.text === tag);
    map[tag] = hit ? hit.i : null;
    if (hit) {
      await checkboxes.nth(hit.i).click({ force: true });
      await page.waitForTimeout(80);
    }
  }

  // conditionSnippet phải chứa "HOẶC". Nếu là "VÀ" -> chạy BƯỚC 1B.
  const body = await page.evaluate(() => document.body.innerText);
  const idx = body.indexOf('Điều kiện');
  return { map, missing: Object.entries(map).filter(([, v]) => v === null).map(([k]) => k),
           conditionSnippet: body.slice(idx, idx + 30) };
}

// ============================================================
// BƯỚC 1B - Chỉ chạy khi Điều kiện đang là "VÀ"
// ============================================================
async (page) => {
  await page.locator('text=Điều kiện').last().click();   // mở submenu điều kiện
  await page.waitForTimeout(400);
  await page.locator('text=HOẶC').first().click();       // chọn "Thẻ A HOẶC Thẻ B"
  await page.waitForTimeout(400);
  const body = await page.evaluate(() => document.body.innerText);
  const idx = body.indexOf('Điều kiện');
  return { conditionSnippet: body.slice(idx, idx + 30) };
}

// ============================================================
// BƯỚC 2 - Mở panel ngày + XÁC NHẬN tab "Thời gian tạo"
// ============================================================
async (page) => {
  await page.locator('.filter-by-time').first().click();
  await page.waitForTimeout(600);

  const seg = await page.locator('.ant-segmented').first().evaluate(el => el.outerHTML);
  const createdSelected = /title="Thời gian tạo"[^>]*aria-selected="true"/.test(seg);

  // Mặc định thường là "Thời gian cập nhật" -> bỏ qua bước này là lọc sai toàn bộ.
  if (!createdSelected) {
    await page.locator('text=Thời gian tạo').first().click();
    await page.waitForTimeout(400);
  }

  const segAfter = await page.locator('.ant-segmented').first().evaluate(el => el.outerHTML);
  return { createdSelected: /title="Thời gian tạo"[^>]*aria-selected="true"/.test(segAfter) };
}

// ============================================================
// BƯỚC 3A - Khoảng ngày TÙY CHỈNH (dùng khi quick-pick không khớp ý user)
// Ví dụ: hôm nay là 08/09 nhưng user muốn tháng 7 -> nút "Tháng trước" sẽ ra tháng 8, SAI.
// ============================================================
async (page) => {
  const START = '01/07/2026 00:00:00';
  const END   = '31/07/2026 23:59:59';

  const startBox = page.getByRole('textbox', { name: 'Ngày bắt đầu' });
  const endBox   = page.getByRole('textbox', { name: 'Ngày kết thúc' });

  // PHẢI dùng .type() - .fill() làm ô còn lại bị xoá trắng (đã đo nhiều lần).
  await startBox.click(); await startBox.fill(''); await startBox.type(START, { delay: 20 });
  await page.waitForTimeout(300);
  await endBox.click();   await endBox.fill('');   await endBox.type(END,   { delay: 20 });
  await page.waitForTimeout(300);

  const startVal = await startBox.inputValue();
  const endVal   = await endBox.inputValue();
  // CẢ HAI phải có giá trị trước khi bấm Lọc. Nếu một ô trắng -> lặp lại bước này.
  if (!startVal || !endVal) return { ok: false, startVal, endVal };

  await page.getByRole('button', { name: 'Lọc' }).click();
  await page.waitForTimeout(1500);

  // Đối chiếu tên đầu danh sách với page-<id>-ordered.json trước khi chạy tiếp!
  const names = (await page.locator('.rc-virtual-list-holder-inner > *').allInnerTexts())
    .slice(0, 3).map(t => t.split('\n')[0]);
  return { ok: true, startVal, endVal, firstThreeNames: names };
}

// ============================================================
// BƯỚC 3B - Dự phòng: chọn ngày bằng cách click ô lịch
// Dùng khi ô nhập text bị loạn. Lưu ý phải force:true (có div trong suốt chặn click).
// ============================================================
async (page) => {
  const MONTHS_BACK = 2;   // số lần bấm prev để panel trái về đúng tháng cần
  const START_IDX = 0;     // ô ngày 1 của tháng bên trái
  const END_IDX = 30;      // ô ngày 31 của tháng bên trái (0-based)

  const prevBtn = page.locator('[class*="prev-btn"]:not([class*="super"])').first();
  for (let i = 0; i < MONTHS_BACK; i++) { await prevBtn.click(); await page.waitForTimeout(200); }

  // Chỉ lấy ô "in-view" (ngày thuộc đúng tháng đang hiển thị)
  const cells = page.locator('.ant-picker-cell.ant-picker-cell-in-view .ant-picker-cell-inner');
  await cells.nth(START_IDX).click({ force: true });
  await page.waitForTimeout(300);
  await cells.nth(END_IDX).click({ force: true });
  await page.waitForTimeout(300);

  // Thứ tự start/end có thể bị đảo -> luôn đọc lại và sửa bằng .type() nếu cần
  const startVal = await page.getByRole('textbox', { name: 'Ngày bắt đầu' }).inputValue();
  const endVal   = await page.getByRole('textbox', { name: 'Ngày kết thúc' }).inputValue();
  return { startVal, endVal };
}
