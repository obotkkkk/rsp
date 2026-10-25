# VanGioi Mob Studio — ánh xạ ID ↔ tên hiển thị

## File nào dùng làm gì?

- `model_names.json`: file tổng hợp có 3 danh sách `models`, `items`, `sounds`; mỗi phần tử có `id` và `name`. Được tạo từ `model_names.json` ban đầu và đối chiếu với `catalog.json` mà bạn cung cấp.
- `names.json`: định dạng mà `index.html` trong bản website hiện tại đang tải (`fetch('names.json')`) để đổi tên hiển thị ở tab Model. Đặt file này cùng cấp với `index.html`. File này cũng khắc phục request `/names.json` bị 404 nếu nguyên nhân là thiếu file.
- `model_id_name_map.csv`: bảng tra cứu ID ↔ tên model, kèm category, đường dẫn blueprint `.bbmodel`, tên liên quan từ cấu hình và nguồn tên. Mở được bằng LibreOffice Calc hoặc Excel.

## Cách dùng

1. Sao lưu `names.json` / `model_names.json` đang có.
2. Nếu muốn website hiện tên Model, chép `names.json` vào thư mục gốc website — cùng thư mục `index.html`.
3. Muốn sửa tên thủ công, mở `names.json` và sửa giá trị bên phải ID; không đổi khóa ID ở bên trái. Ví dụ: `"abyssal_knight": "Ma Ảnh Kị Vương"`.
4. `model_names.json` là bảng tổng hợp có thể chỉnh sửa làm dữ liệu nguồn; website hiện tại không tự đọc file này trực tiếp. Nếu chỉnh file này, hãy đồng bộ thay đổi tương ứng vào `names.json`.

## Cách đặt tên

Tên cho model chính ưu tiên tên hiển thị trong dữ liệu MythicMobs khi có; tên VFX và các mục chưa có tên hiển thị xác thực dùng tên ID đã đổi `_` thành dấu cách, tránh tự bịa tên riêng. Tên của một số hiệu ứng có thể vẫn là tên kỹ thuật. `id` luôn được giữ nguyên để không làm hỏng liên kết tài nguyên.
