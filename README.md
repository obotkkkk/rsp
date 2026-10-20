# VanGioi Mob Studio – bản web (pack nằm cùng host)

Người dùng chỉ cần **mở web → tick quai/boss → Tạo ZIP**. Web tự tải dữ liệu model từ thư mục `pack/` ngay trên host,
không ai phải tìm hay chọn file pack. Mọi xử lý chạy trong trình duyệt người dùng; host **không** nhận hay lưu file ZIP của ai.

## Cấu trúc
```
index.html
.nojekyll
lib/            three.min.js, fflate.min.js
VanGioi_Full_Pack.zip                      <- ZIP nguồn để chạy lại generator; không bắt buộc đưa lên host
pack/data/       manifest.json, version.json, items/, models/, sounds/, resources/, assets/auxiliary.zip
pack/blueprint.json                         <- tuỳ chọn: thứ tự/nhóm model cho tab Model
pack/mobs.zip.001, mobs.zip.002             <- pack cũ, chỉ dùng khi chọn “Dùng pack khác…”
tools/build_web_data.py                     <- tách dữ liệu theo tab từ ZIP nguồn
tools/make_pack.py                           <- tạo pack ZIP cũ cho chế độ tương thích
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
Tạo lại bộ dữ liệu tĩnh dùng cho ba tab bằng lệnh sau từ thư mục dự án:
```
python3 tools/build_web_data.py
```
Mặc định đọc `VanGioi_Full_Pack.zip` cạnh `index.html` và chỉ thay thư mục `pack/data/` do script quản lý. ZIP nguồn không bị sửa. Script dùng `RawZip` vì pack server có CRC/size/local-header metadata giả; payload được kiểm tra bằng giải nén thực và JSON parse. Mọi tài nguyên chưa được phân loại được giữ trong `pack/data/assets/auxiliary.zip`.

Upload toàn bộ `pack/data/` sau khi build. Tab Model tải `version.json` và model index; shard model cùng texture chỉ tải khi xem/render hoặc tạo ZIP. Tab Item và Âm thanh chỉ tải index khi mở; shard Item tải khi bung nhóm, còn audio tải khi bấm nghe/tải.

Blueprint host là tuỳ chọn, đặt tại `pack/blueprint.json`:
```
{
   "version": 1,
   "models": [
      {"id": "abyssal_charge", "group": "abyssal", "order": 1}
   ]
}
```
`id` phải trùng ID model ở `pack/data/models/index.json`; model không khai báo vẫn xuất hiện sau các mục được sắp xếp. File thiếu/sai schema được bỏ qua; bản hợp lệ gần nhất có thể dùng từ IndexedDB khi mạng lỗi.

Static host cần phục vụ đúng đường dẫn tương đối và MIME JSON/PNG/OGG. Dùng HTTPS cho host công khai; `version.json` được revalidate, các file dữ liệu còn lại dùng URL có build ID để cache không giữ nhầm phiên bản cũ. Website không gửi tên, layout hay file người dùng lên server.

Để tạo riêng pack ZIP tương thích cũ, vẫn có thể chạy:
```
python3 tools/make_pack.py VanGioi_Full_Pack.zip
```
Lệnh này ghi lại `pack/mobs.zip.001, .002…` (đã bỏ phần đồ vật/HUD không cần, sửa luôn checksum PNG). Upload các file mới lên host.
Dùng thẳng Full pack cũng được: đặt `pack/VanGioi_Full_Pack.zip` (83 MB, GitHub cho phép < 100 MB, nhưng tải nặng hơn ~3 lần).

## Tên hiển thị trong game (tuỳ chọn)
Sau khi chạy `python3 tools/build_web_data.py`, mở `pack/data/names.json` để điền nhãn cho Model, Item/part, Sound hoặc sound event. File được tạo từ ID thật trong RSP; giá trị `""` nghĩa là tiếp tục hiển thị ID. Ví dụ:
```
{
   "schemaVersion": 1,
   "models": {"abyssal_charge": "Tên mob hiển thị"},
   "items": {"penitent_phase_3/blood_sword": "Kiếm máu"},
   "sounds": {"assassin_skills:assasin_attack": "Đòn đánh sát thủ"},
   "soundEvents": {"assassin_skills:assasin_attack": "Sự kiện đòn đánh"}
}
```
Chỉ cần sửa giá trị, giữ nguyên các ID. Chạy lại generator để cập nhật manifest/build ID; tên đã điền sẽ được bảo toàn nếu ID còn trong pack. Upload lại `pack/data/`. Tên do người dùng nhập trực tiếp trong web vẫn có ưu tiên cao hơn tên trong file này.

Các công cụ sao lưu tên trong UI hiện có vẫn dùng `names.json` phẳng tùy chọn cạnh `index.html`; không thay file đó bằng schema grouped `pack/data/names.json`.

## Lưu ý
- Mỗi người dùng tải ~29 MB lần đầu (trình duyệt/CDN cache cho lần sau). GitHub Pages có giới hạn băng thông mềm ~100 GB/tháng ≈ 3.000 lượt tải lần đầu.
- Pack thuộc về server của bạn – chỉ nên đưa lên host công khai nếu bạn được phép phân phối.
- Nếu không tải được `pack/` (mở file trực tiếp, host lỗi…), web tự cho người dùng chọn file pack của họ.
- Yêu cầu trình duyệt bản mới có WebGL, ~1 GB RAM trống.
