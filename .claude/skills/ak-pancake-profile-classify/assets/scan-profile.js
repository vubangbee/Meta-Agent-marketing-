// Chay TREN TAB PROFILE FACEBOOK (tab moi mo tu click avatar), dan nguyen khoi nay vao
// cong cu chay-JS-trong-trang cua trinh duyet (vd browser_run_code_unsafe, page.evaluate,
// hoac tuong duong). Tra ve JSON nho, KHONG chup man hinh trong buoc nay - script nay chi
// la tin hieu chu re, bo sung cho anh chup (xem browser-mechanics.md muc 3).
//
// Da kiem chung: phat hien dung "da khoa bao ve trang ca nhan" (Vo Kim), "Khong co bai viet",
// va SDT dang "0912 345 678" / "0912-345-678" / "0912.345.678" xen trong van ban tuong.

() => {
  const text = document.body.innerText || "";

  const friendsMatch = text.match(/[\d.,]+\s*người bạn/);
  const locked = /đã khóa bảo vệ trang cá nhân/i.test(text);
  const noPosts = /Không có bài viết/i.test(text);

  // 0[35789] + 8 so nua, cho phep khoang trang/cham/gach ngang xen giua tung nhom so.
  const rawPhoneMatches = text.match(/0\s*\d(?:[\s.\-]?\d){8}/g) || [];
  const phones = [...new Set(
    rawPhoneMatches
      .map(p => p.replace(/[\s.\-]/g, ""))
      .filter(p => p.length === 10 && /^0[35789]/.test(p))
  )];

  return {
    url: location.href,
    friends: friendsMatch ? friendsMatch[0] : null,
    locked,
    noPosts,
    phones,
  };
}
