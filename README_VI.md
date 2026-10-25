# VanGioi RSP Pro — Bản Lite Resource Pack Creator

## Khởi động trên Windows

1. Giải nén toàn bộ `VanGioi_RSP_Pro_ReadyToRun.zip` vào một thư mục (giữ nguyên cây thư mục).
2. Mở `START_WINDOWS.bat` (yêu cầu Python 3.10 trở lên). Chương trình chỉ dùng thư viện chuẩn Python, không phải cài `pip install` để chạy.
3. Trình duyệt sẽ mở trang `http://127.0.0.1:8765/`. Nếu không tự mở, sao chép địa chỉ này vào Chrome, Edge hoặc Cốc Cốc.
4. Chọn **Model**, **VFX**, **Item**, **Sound**, tìm ID/tên skill/tên boss/tên vũ khí. Tick những mục cần lấy.
5. Nhấn **Xuất Lite Pack** → đặt tên → **Tạo và tải ZIP**. Không cần thêm asset thủ công khi các quan hệ file đã được xác định từ nguồn.

Các thao tác diễn ra trên `127.0.0.1` (máy tính cá nhân), không gửi resource pack tới dịch vụ ngoài. Khi đóng cửa sổ terminal, trang web cục bộ sẽ dừng hoạt động.

## Chức năng

- Giao diện quản lý Pro với bộ lọc, tìm kiếm dấu tiếng Việt, thông tin nguồn, danh sách chọn riêng cho bốn loại tài nguyên.
- Tìm quan hệ `model / VFX / sound → MythicMobs skill → mob/boss` và `skill → MMOItems ability → vũ khí`, có qua bí danh từ MythicLib.
- Ghi file `.yml` hoặc `.java` đóng vai trò bằng chứng. **Trực tiếp** là khai báo trong cấu hình, **Gián tiếp** là qua chuỗi gọi skill tối đa 6 lớp, **Mã nguồn** là chuỗi định danh được tìm thấy trong Java (không khẳng định lúc nào cũng chạy thực tế).
- Item có `custom-model-data` hợp lệ được liên kết với vũ khí/trang bị bằng cặp **material + CMD** khớp với override trong `assets/minecraft/models/item/<material>.json`.
- Đóng ZIP Lite có tài nguyên phụ thuộc: geometry, model/item JSON, texture, PNG `.mcmeta`, âm thanh `.ogg`, bản `sounds.json` cắt theo sự kiện đã chọn và atlas cho modelengine; có tạo override CMD tối thiểu cho item khớp.
- PNG bị hỏng checksum được sửa khi có thể; ZIP xuất dùng CRC hợp lệ thay vì kiểu CRC sai có chủ đích của source cũ.
- Có `VANGIOI_LITE_REPORT.json` bên trong mỗi ZIP, ghi mục đã chọn và đường dẫn phụ thuộc không tìm thấy.
- Tích hợp Studio 3D ngay trong trang Pro (tab **Model Studio 3D**) để xem model/item, tự sắp model và nạp `.bbmodel` khi cần. Trang `/studio/index.html` vẫn có thể mở độc lập.

## Cấu trúc

```
VanGioi_RSP_Pro/
 ├─ START_WINDOWS.bat
 ├─ app.py                 # server local + Lite exporter, không cần pip
 ├─ index.html             # giao diện Pro
 ├─ studio_integrated.html # Studio gốc đã sửa, giao tiếp với Pro
 ├─ build_catalog.py       # tái tạo quan hệ bằng config (yêu cầu PyYAML)
 ├─ data/catalog.json.gz   # bản đồ liên kết đã tạo sẵn
 └─ packs/
     ├─ VanGioi_Model_Pack.zip
     ├─ VanGioi_Item_Pack.zip
     ├─ VanGioi_ExtraSound_Pack.zip
     ├─ rsp-main.zip              # source viewer gốc + tài nguyên 3D
     ├─ Mythicmobs.zip           # bản gọn: mobs/skills/packs/, không chứa dữ liệu người chơi
     ├─ MMOItems.zip             # bản gọn: item/, không chứa userdata
     ├─ MythicLibs.zip           # bản gọn: skill/
     └─ VanGioiTuTienCore-6.9.3-release-source(1).zip
```

Source đã cung cấp `VanGioi_Full_Pack.zip` và `ModelEngine.zip` được dùng để đối chiếu dữ liệu ban đầu; chúng không bắt buộc ở runtime và không có trong gói ReadyToRun để tránh lặp lại hàng trăm MB. Blueprint gốc không tự động nạp toàn bộ vào Studio 3D; có thể dùng nút **Nạp blueprint** trong giao diện gốc để tải file `.bbmodel` hoặc ZIP chứa blueprint phù hợp.

## Phạm vi xác minh & lưu ý kỹ thuật

- Hệ thống chỉ lập chỉ mục từ file đã cung cấp. **Không tìm thấy liên kết** không có nghĩa tài nguyên không được dùng trên server. Runtime script bằng Skript, reflection, command hoặc các plugin chưa gửi có thể không có trong bản đồ này.
- Tài nguyên phức tạp và định danh sử dụng plugin như ModelEngine/MythicMobs/MMOItems vẫn đòi cấu hình server và quy trình build/plugin tương ứng. Một ZIP RSP không tự biến VFX thành kỹ năng hoạt động.
- VFX được nhận diện từ tên/đường dẫn blueprint; đây là phân loại heuristic, không phải chứng cứ nó có gán skill.
- Với một số file `models/item` có nhiều override phụ thuộc, dung lượng Lite có thể lớn vì phải giữ các phụ thuộc thực tế.
- Kết quả được kiểm thử bằng ZIP library (CRC hợp lệ), kiểm tra xuất kết hợp model/item/sound và thử cấu hình CMD. **Chưa có bằng chứng kiểm thử trực tiếp trên Minecraft client/server đang chạy**.
- Có 1 file YAML lỗi đọc trong nguồn gửi khi tạo chỉ mục; không được suy diễn những quan hệ nằm trong file không đọc được.

## Tạo lại catalog từ cấu hình server mới

Nếu sửa các file YAML/JAVA, thay những ZIP trong `packs/` rồi chạy:

```
py -3 -m pip install PyYAML
py -3 build_catalog.py
```

Nếu muốn đối chiếu vị trí blueprint khi build lại, đặt thêm `ModelEngine.zip` bản gốc ở `packs/`. Chương trình tự quét các file `.bbmodel` có ID khớp; blueprint thiếu không ảnh hưởng khả năng tạo ZIP Lite.

## Chẩn đoán

- Cổng `8765` đang dùng: chạy `set RSP_PORT=8766` rồi `py -3 app.py`.
- Có thiếu dependency trong ZIP xuất: mở `VANGIOI_LITE_REPORT.json`, mục `missing` để biết đường dẫn không tìm thấy.
- Source web gốc có bộ xem 3D và cách lưu/tải dữ liệu riêng, chạy sau khi trang tải đủ source model split ZIP. Giao diện Pro chạy độc lập, không chờ bộ xem 3D.
- Không đổi tên và không giải nén các resource pack ZIP bên trong `packs/`.


## Cập nhật Studio tích hợp v2.1
- Model Studio 3D được nhúng trong giao diện Pro (cùng trang, cùng danh sách), không còn cần mở tab riêng.
- Checkbox bên danh sách Pro chọn asset để xuất Lite; nút **Xem Model Studio 3D** hoặc tab Studio xem bản dựng tương ứng.
- Trong Studio 3D, click tick model sẽ đồng thời mở preview và cập nhật lựa chọn Lite Pack.
- Gõ tìm kiếm theo tên boss, quái, vũ khí, skill, công pháp hoặc ID. Gợi ý sử dụng quan hệ xác minh từ file cấu hình.
- Một số Item dạng JSON chỉ có đường dẫn resource mà không có hình học trong Studio gốc: phần xem trước sẽ báo rõ nếu không tìm được model tương ứng.
- Cần trình duyệt hỗ trợ WebGL, bật tăng tốc phần cứng nếu canvas không hiển thị.
