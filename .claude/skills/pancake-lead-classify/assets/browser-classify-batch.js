// Chạy MỘT LÔ phân loại: paste nguyên khối này vào browser_run_code_unsafe.
// Chỉ sửa EXPECTED_NAMES = một lát cắt LIÊN TỤC 15-25 tên từ page-<id>-names.json,
// đúng thứ tự, bắt đầu từ đúng chỗ lô trước dừng lại.
//
// Trả về mảng {expected, status, stageBefore, action} - JSON nhỏ, tiết kiệm token.
// KHÔNG chụp màn hình trong lô; chỉ chụp khi cần triage bug thật.
//
// TIỀN ĐIỀU KIỆN: cửa sổ trình duyệt phải rộng >= 1300px (browser_resize width:1400).
// Hẹp hơn, Pancake thu gọn giao diện và KHÔNG render icon ⓘ lẫn nút "Xem trên Facebook"
// -> toàn bộ lô trả NO_INFO_PANEL / waitForEvent timeout dù code đúng.
//
// Đã kiểm chứng trên 333 hội thoại. Đừng "tối ưu" các con số delay/scroll bên dưới:
//   - 12px/bước: bước lớn hơn gây vọt qua dòng (đã bỏ sót 2 hội thoại vì nhảy theo công thức).
//   - exact:true: thiếu nó sẽ khớp cả "Không đủ tiêu chuẩn" (đã đặt nhầm 1 khách).
//   - ensureInfoOpen: nút ⓘ là TOGGLE, trạng thái panel giữ lại giữa các hội thoại.

async (page) => {
  const EXPECTED_NAMES = [
    // "Thao Ho", "Lê Thị Thu Liễu", ...
  ];

  const results = [];
  const scroller = page.locator('.rc-virtual-list-holder').first();
  const rows = page.locator('.rc-virtual-list-holder-inner > *');

  // Quét cửa sổ render để tìm tên, cuộn thô 600px mỗi nấc cho app lazy-load thêm.
  // KHÔNG nhảy một phát khoảng cách lớn: scrollHeight chỉ bao vùng đã nạp nên cú nhảy
  // bị kẹp lại (đo 2026-09-09: nhắm pos81 nhưng dừng ở pos51).
  // Trả về chỉ số k trong cửa sổ hiện tại -> click thẳng rows.nth(k), không cần đưa lên đầu.
  // Nhờ vậy đi được khoảng cách xa tuỳ ý VÀ xử lý luôn phần đuôi danh sách.
  async function findIndex(name) {
    for (let pass = 0; pass < 2; pass++) {
      let lastTop = -1;
      for (let i = 0; i < 120; i++) {
        const names = (await rows.allInnerTexts()).map(t => t.split('\n')[0]);
        const k = names.indexOf(name);
        if (k >= 0) return k;
        const top = await scroller.evaluate(el => { el.scrollTop += 600; return el.scrollTop; });
        await page.waitForTimeout(400);
        if (top === lastTop) break;          // chạm đáy, không nạp thêm được
        lastTop = top;
      }
      await scroller.evaluate(el => el.scrollTop = 0);   // quét lại từ đầu phòng đã vọt qua
      await page.waitForTimeout(600);
    }
    return -1;
  }

  // Nút ⓘ mở/đóng cùng một panel -> phải kiểm tra kết quả, không click mù.
  async function ensureInfoOpen() {
    const btn = page.locator('.open-in-messenger-button').first();
    for (let attempt = 0; attempt < 2; attempt++) {
      if (await btn.count() && await btn.isVisible()) return true;
      await page.locator('.conv-action-btn.color-primary').first().click();
      await page.waitForTimeout(500);
    }
    return (await btn.count()) > 0 && await btn.isVisible();
  }

  for (const expected of EXPECTED_NAMES) {
    const k = await findIndex(expected);
    if (k < 0) { results.push({ expected, status: 'NOT_FOUND' }); continue; }

    // Xác minh lại NGAY TRƯỚC KHI CLICK: cửa sổ render có thể đã dịch sau lần cuộn cuối.
    // Lệch tên = nguy cơ phân loại nhầm người -> không click, ghi nhận và đi tiếp.
    const nameAtK = (await rows.nth(k).innerText()).split('\n')[0];
    if (nameAtK !== expected) { results.push({ expected, found: nameAtK, status: 'MISMATCH' }); continue; }

    await rows.nth(k).click();
    await page.waitForTimeout(700);

    if (!(await ensureInfoOpen())) {
      results.push({ expected, status: 'NO_INFO_PANEL' });
      continue;
    }

    let stageBefore = null, stageAfter = null, err = null, action = 'none';
    try {
      const [fbPage] = await Promise.all([
        page.context().waitForEvent('page', { timeout: 8000 }),
        page.locator('.open-in-messenger-button').first().click(),
      ]);
      await fbPage.waitForLoadState('domcontentloaded');
      await fbPage.waitForTimeout(3500);

      const combo = fbPage.getByRole('combobox', { name: /Stage Selector/i }).first();
      stageBefore = (await combo.innerText({ timeout: 6000 })).replace(/\s+/g, ' ').trim();

      if (!stageBefore.startsWith('Đủ tiêu chuẩn')) {
        await combo.click();
        await page.waitForTimeout(500);
        // exact:true BẮT BUỘC - "Không đủ tiêu chuẩn" chứa chuỗi "Đủ tiêu chuẩn"
        await fbPage.getByRole('option', { name: 'Đủ tiêu chuẩn', exact: true }).click();
        await page.waitForTimeout(1000);
        stageAfter = (await combo.innerText({ timeout: 6000 })).replace(/\s+/g, ' ').trim();
        action = 'set';
      }
      await fbPage.close();
    } catch (e) {
      err = e.message.slice(0, 150);
      // Dọn tab Facebook lạc, nếu không sẽ tích tụ hàng chục tab rác
      const stray = page.context().pages().find(p => p.url().includes('business.facebook.com'));
      if (stray) await stray.close();
    }

    results.push({
      expected,
      status: err ? 'FB_ERROR:' + err : 'ok',
      stageBefore,
      stageAfter,
      action,
    });
  }

  return results;
}
