# Hướng dẫn VanGioi Mob Studio

Tài liệu này hướng dẫn (1) đổi tên hiển thị để dễ tìm model thay vì chỉ nhìn ID và (2) thêm file blueprint `.bbmodel`.

## 1. Đổi tên hiển thị của model từ ID sang tên dễ hiểu

### Cách đổi ngay trên website

1. Mở VanGioi Mob Studio bằng địa chỉ HTTP/HTTPS.
2. Chọn tab **Model**.
3. Tìm model bằng ô tìm kiếm. Có thể gõ một phần ID đang có.
4. Ở dòng model, nhập tên dễ nhớ vào ô tên nằm phía trên dòng ID nhỏ màu chữ phụ. Ví dụ:
   - ID: `abyssal_knight`
   - Tên hiển thị: `Hiệp sĩ vực thẳm`
5. Chờ website tự lưu. Nếu hiện thông báo lỗi lưu tên hoặc khi tải lại tên bị mất, máy chủ hiện tại có thể không hỗ trợ API ghi tên; xem cách sửa dữ liệu nguồn bên dưới.

**Lưu ý:** cách này chỉ đổi tên hiển thị trong công cụ, không đổi ID tài nguyên Minecraft. Giữ nguyên ID là cách an toàn nhất để tránh làm hỏng đường dẫn model/texture trong RSP.

### Sửa tên mặc định trong dữ liệu nguồn

Nếu muốn tên được dùng làm mặc định sau khi build lại website:

1. Mở file `model_names.json` bằng trình soạn thảo văn bản.
2. Tìm mục có ID cần sửa. Ví dụ:

   ```json
   {
     "id": "abyssal_knight",
     "name": "abyssal_knight"
   }
   ```

3. Chỉ sửa giá trị `name`, giữ nguyên `id`. Ví dụ:

   ```json
   {
     "id": "abyssal_knight",
     "name": "Hiep si vuc tham"
   }
   ```

4. Lưu file, build lại dữ liệu/website theo quy trình của dự án rồi tải lại trang bằng `Ctrl+Shift+R`.

Giữ đúng cú pháp JSON: dùng dấu ngoặc kép, không thêm dấu phẩy sau mục cuối và không đổi tên trường `id`/`name`.

## 2. Thêm file `.bbmodel`

File `.bbmodel` dùng trong công cụ này để lấy cây bone và vị trí lắp ráp blueprint. Nó không tự biến toàn bộ hình học Blockbench thành model Minecraft mới.

### Cách A — Nạp nhanh ngay trong website

1. Mở tab **Model** và chọn model muốn xem.
2. Bấm **Nạp blueprint…**.
3. Chọn một hoặc nhiều file `.bbmodel`; có thể chọn file `.zip` chứa nhiều `.bbmodel`.
4. Tên file (bỏ phần mở rộng `.bbmodel`) cần trùng ID model trong danh sách. Ví dụ ID `abyssal_knight` thì tên file phải là `abyssal_knight.bbmodel`.
5. Khi nạp xong, đọc thông báo kết quả. Nếu báo không có model trùng tên, hãy đổi tên file cho đúng ID rồi nạp lại.
6. Chọn chế độ **Lắp ráp theo blueprint** nếu muốn xem vị trí lắp theo blueprint.

Cách này phù hợp để thử nhanh trong phiên đang mở. Nếu cần blueprint được phân phối cùng website cho tất cả người dùng, hãy dùng Cách B.

### Cách B — Đưa blueprint vào website để dùng lâu dài

1. Trong thư mục website, tạo/mở thư mục `blueprints/` (chữ thường).
2. Chép file vào đó, đặt tên khớp ID. Ví dụ:

   ```text
   blueprints/abyssal_knight.bbmodel
   ```

3. Mở `blueprints/index.json` và thêm đường dẫn tương đối vào mảng `files`. Ví dụ:

   ```json
   {
     "files": [
       "abyssal_knight.bbmodel",
       "bosses/dragon_boss.bbmodel"
     ]
   }
   ```

4. Với ví dụ thứ hai, hãy tạo thư mục `blueprints/bosses/` và đặt file `dragon_boss.bbmodel` vào đó.
5. Tải toàn bộ website đã cập nhật lên host, bảo đảm file `.bbmodel` và `blueprints/index.json` được tải lên cùng nhau.
6. Mở website rồi nhấn `Ctrl+Shift+R` để tải mới.

Nếu host không cho phép liệt kê thư mục, `blueprints/index.json` là cách nên dùng vì website có danh sách đường dẫn cụ thể để tải. JSON phải hợp lệ, không có dấu phẩy thừa hoặc chú thích.

### Nếu blueprint không nhận

- Kiểm tra tên file có trùng chính xác ID model không; nên dùng chữ thường, không dấu cách và không thêm hậu tố như ` (1)`.
- Mở file trong Blockbench, xác nhận đó là `.bbmodel` hợp lệ và có `outliner`/bone.
- Nếu dùng Cách B, kiểm tra URL của file `.bbmodel` và `blueprints/index.json` không trả về `404`.
- Tải lại trang bằng `Ctrl+Shift+R` sau khi cập nhật.
- Nếu danh sách báo trùng ID, chỉ giữ một blueprint cho mỗi ID.

## 3. Ghi nhớ

- **Tên hiển thị** và **ID tài nguyên** là hai thứ khác nhau. Đổi tên hiển thị không tự đổi ID trong RSP.
- Blueprint phải khớp ID để công cụ tìm đúng model.
- Nên giữ bản sao lưu `model_names.json`, `blueprints/index.json` và các file `.bbmodel` trước khi sửa.
