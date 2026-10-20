# VanGioi Mob Studio – bản web (pack nằm cùng host)

Người dùng chỉ cần **mở web → tick quai/boss → Tạo ZIP**. Web tự tải dữ liệu model từ thư mục `pack/` ngay trên host,
không ai phải tìm hay chọn file pack. Mọi xử lý chạy trong trình duyệt người dùng; host **không** nhận hay lưu file ZIP của ai.

## Cấu trúc
```
index.html
.nojekyll
lib/            three.min.js, fflate.min.js
pack/           mobs.zip.001, mobs.zip.002   <- dữ liệu model quái/boss (rút gọn từ VanGioi_Full_Pack.zip, ~29 MB)
tools/make_pack.py                           <- tạo lại pack/ khi server cập nhật pack
names.json      (tuỳ chọn) tên hiển thị trong game cho mọi người
layouts.json    (tuỳ chọn) bố cục lắp ráp mảnh dùng chung
```

## Đưa lên GitHub Pages (miễn phí)
1. Tạo repo mới (Public).
2. Upload **toàn bộ** thư mục này (kể cả `pack/` và `.nojekyll`). Mỗi phần pack ≤ 20 MB nên upload qua web được (GitHub web giới hạn 25 MB/file).
   *Nếu dùng git: `git add . && git commit -m web && git push`.*
3. *Settings → Pages → Deploy from a branch → main / (root) → Save.* Sau ~1 phút có địa chỉ `https://<tên-bạn>.github.io/<tên-repo>/`.

Cloudflare Pages / Netlify: kéo thả cả thư mục (mỗi file < 25 MB nên đều qua được).

## Khi server cập nhật pack
```
python3 tools/make_pack.py VanGioi_Full_Pack.zip
```
Lệnh này ghi lại `pack/mobs.zip.001, .002…` (đã bỏ phần đồ vật/HUD không cần, sửa luôn checksum PNG). Upload các file mới lên host.
Dùng thẳng Full pack cũng được: đặt `pack/VanGioi_Full_Pack.zip` (83 MB, GitHub cho phép < 100 MB, nhưng tải nặng hơn ~3 lần).

## Tên hiển thị trong game (tuỳ chọn)
Trên web nhập tên từng con (hoặc "Nhập tên…" từ `.yml` MythicMobs) → bấm **Xuất tên** → đặt `names.json` cạnh `index.html`. Ai mở web cũng thấy sẵn tên. Tương tự **Xuất bố cục** → `layouts.json`.

## Lưu ý
- Mỗi người dùng tải ~29 MB lần đầu (trình duyệt/CDN cache cho lần sau). GitHub Pages có giới hạn băng thông mềm ~100 GB/tháng ≈ 3.000 lượt tải lần đầu.
- Pack thuộc về server của bạn – chỉ nên đưa lên host công khai nếu bạn được phép phân phối.
- Nếu không tải được `pack/` (mở file trực tiếp, host lỗi…), web tự cho người dùng chọn file pack của họ.
- Yêu cầu trình duyệt bản mới có WebGL, ~1 GB RAM trống.
