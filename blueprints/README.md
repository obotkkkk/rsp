# Hướng dẫn thêm và đổi tên file `.bbmodel`

## Cách nhanh

1. Mở thư mục website, nơi có `index.html`. Tạo thư mục `blueprints` nếu chưa có. Đường dẫn phải là `blueprints/` viết thường.
2. Chép file `.bbmodel` đã xuất từ Blockbench vào thư mục đó.
3. Đổi tên file thành **đúng ID model** đang hiển thị trong danh sách Model, không phải tên hiển thị tuỳ chỉnh. Ví dụ: `abyss_charge.bbmodel`. Dùng một file cho mỗi ID; nên viết thường và bỏ hậu tố tự sinh như ` (1)`.
4. Tải lại website. File được nạp tự động nếu host cho đọc danh sách thư mục. Nếu host không cho directory listing, thêm đường dẫn file vào `blueprints/index.json` như hướng dẫn bên dưới.

## Cấu hình manifest (khuyên dùng cho host tĩnh)

Sửa `blueprints/index.json` thành danh sách đường dẫn tương đối từ thư mục `blueprints/`, ví dụ:

```json
{
  "files": [
    "abyss_charge.bbmodel",
    "crowaxe.bbmodel",
    "bosses/dragon_boss.bbmodel"
  ]
}
```

Tạo thư mục con như `blueprints/bosses/` nếu cần; với đường dẫn trong manifest, website sẽ tải trực tiếp file, không cần directory listing. Tên file chỉ lấy phần tên cuối để so khớp ID, do đó `bosses/dragon_boss.bbmodel` khớp ID `dragon_boss`.

## Lưu ý

- File phải là `.bbmodel` hợp lệ do Blockbench lưu, có `outliner`/bone. Blueprint dùng để lấy cây bone và vị trí lắp; đây không phải cách nhập toàn bộ hình học của file Blockbench thành model Minecraft.
- Tên file phải khớp ID model. Nếu không khớp, website vẫn bỏ qua blueprint đó cho việc lắp model và ghi cảnh báo trong console trình duyệt.
- Nếu thư mục hoặc manifest không tồn tại, không có `.bbmodel`, hoặc file không tải được, website tự bỏ qua và vẫn hoạt động bình thường. Không cần tạo dữ liệu giả.
- Khi sửa `index.json`, JSON phải hợp lệ: không có dấu phẩy thừa hoặc chú thích.
- Nếu đổi file trên host mà trình duyệt còn giữ phiên cũ, tải lại trang bằng `Ctrl+Shift+R`.
