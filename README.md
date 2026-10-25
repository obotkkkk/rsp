# VanGioi Mob Studio – website Model / Item

Website tĩnh chạy trong trình duyệt. Tab **Model** tải danh sách model từ pack nguồn, cho xem 3D, lắp ráp/blueprint và tạo ZIP các model đã tick. Tab **Item** đọc index Item RSP được build sẵn, tải chi tiết theo nhóm khi cần và xem preview 3D của từng item. Bộ lọc, nhóm mở rộng, trạng thái tick và mục đang xem của hai tab được tách riêng.

Các nút **Thank** và **Wiki** mở lần lượt `https://github.com/obotkkkk` và `https://vangioiwiki.netlify.app/`. Chức năng **Tạo ZIP** áp dụng theo tab đang mở, bao gồm Model và Item.

## Cấu trúc chính

```text
index.html
.nojekyll
lib/                         three.min.js, fflate.min.js
blueprints/                  .bbmodel tuỳ chọn + index.json
pack/mobs.zip.001, .002      dữ liệu Full RSP rút gọn cho tab Model
pack/data/items/index.json   index nhóm/item từ Item RSP
pack/data/items/*.json       chi tiết item theo nhóm, tải theo nhu cầu
pack/data/resources/         texture đã chuẩn hoá cho preview item
tools/build_web_data.py      tạo dữ liệu tĩnh cho web từ Full RSP + Item RSP
tools/make_pack.py           công cụ tạo pack Model gọn để chạy web
```

## Triển khai

Đưa toàn bộ nội dung trong `dist/VanGioi_Web_SRC.zip` lên host tĩnh hoặc giải nén thư mục triển khai rồi phục vụ bằng HTTP(S). Không mở bằng `file://`: trình duyệt cần HTTP(S) để fetch index, dữ liệu item và texture.

## Thêm blueprint `.bbmodel`

Đặt file cạnh website tại `blueprints/<model-id>.bbmodel`. Tên file (không tính đuôi `.bbmodel`) phải trùng ID model trong danh sách, ví dụ `abyss_charge.bbmodel`. Website thử đọc `blueprints/index.json`; nếu danh sách rỗng/không có manifest, website thử tự quét `/blueprints/` khi host cho phép directory listing. Với host tắt directory listing, ghi rõ tên file vào `blueprints/index.json`. Nếu không có thư mục/file hoặc blueprint lỗi, website tự bỏ qua. Hướng dẫn chi tiết nằm trong [`blueprints/README.md`](blueprints/README.md) và [`BLUEPRINTS_HUONG_DAN.md`](BLUEPRINTS_HUONG_DAN.md).

## Build lại dữ liệu

Đặt hai file nguồn cạnh script:
- `VanGioi_Full_Pack.zip`
- `VanGioi_Item_Only.zip`

Chạy:

```bash
python3 tools/build_web_data.py
```

Công cụ tạo dữ liệu model/item/audio và ZIP triển khai trong `dist/`. Những file trong thư mục `blueprints/` được đưa vào ZIP triển khai khi build. Không tự bù mục bị thiếu; các tham chiếu thiếu phải được xem trong báo cáo build. Nên giữ lại `BUILD_REPORT.json` để đối chiếu số lượng nguồn/đầu ra.

## Lưu ý

- Trang cần trình duyệt hiện đại hỗ trợ WebGL.
- Lần đầu tab Model tải pack chia phần; tab Item đọc index khi được mở và chỉ fetch JSON nhóm khi cần.
- Texture item được nạp từ `pack/data/resources/` khi không có trong Full RSP.
- Chỉ công khai pack/blueprint nếu bạn có quyền phân phối dữ liệu đó.

## Giới hạn bảo vệ mã nguồn và RSP

ZIP triển khai áp dụng lớp cản cơ bản cho menu chuột phải/phím tắt xem mã nguồn; khi môi trường build có Node.js và TypeScript, JavaScript inline được parse rồi compact để bỏ định dạng/comment. Nếu thiếu parser, script giữ nguyên JavaScript để tránh làm hỏng cú pháp. Đây chỉ là biện pháp gây khó cho việc xem nhanh; mã JavaScript vẫn phải gửi tới trình duyệt nên người có kinh nghiệm vẫn có thể lấy và phân tích được. Không dùng cơ chế vòng lặp `debugger` hoặc khóa trình duyệt để tránh làm treo trang.

RSP được tạo từ lựa chọn Model và Item vẫn dùng cấu trúc ZIP/resource path mà Minecraft vanilla cần. Sau khi tạo, website cố ý đổi CRC trong local header và central directory của ZIP, nhưng **không đổi byte dữ liệu model/JSON/texture**. Vì vậy, các công cụ xác minh CRC thường báo `Bad CRC` khi kiểm tra/giải nén; kiểm thử mẫu cho thấy Java `ZipFile` và ZIP filesystem vẫn đọc được nội dung. Dẫu vậy, chưa có kiểm thử trực tiếp trong phiên Minecraft đang chạy — hãy thử pack nhỏ trước khi phát hành rộng.

Đây chỉ là cách gây khó, không phải mã hóa: một công cụ bỏ qua CRC, sửa CRC hoặc giải nén rồi đóng gói lại vẫn có thể lấy dữ liệu. Một số trình giải nén có thể vẫn giữ lại file dù hiển thị lỗi CRC. ZIP nguồn được website tải làm đầu vào (`pack/mobs.zip.*`) vẫn giữ CRC hợp lệ; chỉ RSP đầu ra do nút **Tạo ZIP** tạo cho Model/Item mới được áp dụng CRC sai có chủ đích.
