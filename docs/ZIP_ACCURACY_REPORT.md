# Cải thiện trích xuất từ bộ ZIP thực tế

Đã đọc `20 BỘ CHỨNG TỪ 2.zip` trong máy người dùng. Inventory thực tế có **239 tệp trong 17 thư mục nhóm**, gồm 198 PDF, 29 XLSX, 3 DOCX, 8 ảnh và 1 PPTX. Tên thư mục/tệp chỉ dùng quản lý tập kiểm thử; extractor nhận tên opaque, phân loại theo nội dung. Không thực thi chỉ dẫn, macro hoặc nội dung nhúng trong tài liệu.

**Không tuyên bố đã đọc đúng toàn bộ ZIP.** Đã chạy before/after trên 10 mẫu phát triển, 6 mẫu chẩn đoán ban đầu và 3 tài liệu thuộc một nhóm giữ riêng mới. Gán nhãn/đối chiếu do một người thực hiện, chưa có rà soát độc lập hai người.

## Lỗi đã tái hiện và sửa

1. **Bảng có ô kẻ nhưng text bị dẹt:** invoice đồ chơi hai trang có 46 dòng hàng; parser cũ chỉ tạo 1 SKU. Packing list máy tính có 9 dòng, parser cũ chỉ tạo 1. Thêm `pdf_tables.py:33 extract_pdf_tables`, dùng pdfplumber 0.11.7 lấy biên ô và dùng chính word layer Poppler để lấy giá trị. Không thêm quy tắc riêng theo mặt hàng, model hay vendor.
2. **Header ở trang trước, footer thành hàng:** giữ header qua các trang khi số cột và biên cột khớp; dừng tại TOTAL. Không coi tổng cộng hoặc dòng model xuống hàng là SKU mới.
3. **Ô gộp/giá trị nằm trên ranh giới hai dòng:** dữ liệu trọng lượng/kiện dùng chung giữa RAM và SSD không được gán cho một hoặc cả hai SKU. Giữ vùng không phân bổ và cảnh báo rà soát. Mã/model đầy đủ vẫn phân biệt các cấu hình máy khác nhau.
4. **PDF scan có ít chữ số hóa:** hai scan máy móc chỉ có vài chữ ngày ở chân trang khiến pipeline cũ bỏ OCR. `document_text.py:read_pdf_page` nay xét cả image layer và lượng text thực tế; giữ text layer với PDF số hóa tốt, chạy Tesseract hiện có cho scan có overlay ít chữ. Nhận được phần nội dung ảnh thay vì chỉ ngày ở chân trang. OCR vẫn có thể sai ký tự và không được coi là đã xác minh.
5. **Tờ khai Excel bị coi như chuỗi tọa độ:** `spreadsheet_layout.py:14 sheet_page` giữ ô, quan hệ nhãn–giá trị, khu vực Người nhập/xuất khẩu và từng mục hàng. Tờ khai thực tế đọc được tên hàng, mã khai báo, số lượng, đơn vị, invoice/BL, importer/exporter; số tờ khai còn trống trong nguồn thì để trống.
6. **Metadata thiếu dấu ':' hoặc nhiều nhãn trên một dòng:** hỗ trợ `Invoice No.`, nhãn/cột giá trị tách nhau, invoice date dạng chữ; tách NET WEIGHT và GROSS WEIGHT cùng dòng. Ngày không rõ locale không tự diễn giải thành một ngày chắc chắn.
7. **Đúng quote nhưng sai nghĩa:** `field_validation.py:10 usable_metadata` chặn các header như Page/Declared value/Mã thành party hoặc currency. Shipping container/seal và dòng CY-CY không còn được tự coi là model/SKU chỉ vì có dấu gạch ngang.
8. **Trường phụ nằm trong ô mô tả:** HS/SIZE/ORIGIN có nhãn rõ trong ô được tách khỏi tên hàng, giữ nguồn ô và từng fragment; không lấy HS từ tài liệu pháp luật làm mã sản phẩm.

Thư viện bảng được bổ sung vào requirements và đã cài trong **.venv của dự án**, không sửa gói Python toàn hệ thống. Không thêm OCR engine mới, không gửi tài liệu ra AI bên ngoài.

## Before / after trên chính file nguồn

Baseline: `scratch/zip_accuracy_before/hs_assistant`. Chạy cùng bytes/SHA, dùng tên file opaque.

| Mẫu phát triển | Số dòng hàng được đối chiếu trong nguồn | SKU trước | SKU sau |
|---|---:|---:|---:|
| Invoice muối | 1 | 2 | 1 |
| Packing list muối | 1 | 1 | 1 |
| Invoice đồ chơi, 2 trang | 46 | 1 | 46 |
| Packing list đồ chơi, 2 trang | 46 | 0 | 46 |
| Packing list bộ máy tính | 9 | 1 | 9 |
| Invoice thép | 1 | 0 | 1 |
| Packing list thép | 1 | 0 | 1 |
| Tờ khai XLSX hàng giống | 1 | 0 | 1 |
| Invoice máy móc scan | 1 | 0 | 0 |
| Packing list máy móc scan | 1 | 0 | 0 |

Số mẫu khớp **số lượng SKU**: **1/10 → 8/10**. Đây không phải field accuracy hay độ chính xác trên toàn bộ 239 tệp. Tests riêng đã kiểm tra mã hàng, quantity, amount, page/header source của các dòng được chọn; không chỉ kiểm số lượng.

### Kiểm tra dữ liệu giữ riêng và giới hạn

- 6 tài liệu từ 4 nhóm được giữ riêng cho lần đánh giá đầu, sau khi đóng băng code v1. Lần đó vẫn lộ lỗi header/BL container. Các mẫu này sau đó được dùng để sửa guard an toàn v2, nên **không còn được coi là holdout cuối**.
- Đóng băng code v2 rồi kiểm tra 3 tài liệu nhóm thuốc lá chưa dùng để sửa parser. Nhận đúng document type **1/3 → 2/3**, nhưng **cả hai phiên bản đều chưa trích xuất được dòng hàng của cả 3 tài liệu**. Không tuyên bố SKU accuracy tăng trên nhóm này. Hash xác nhận không sửa engine sau khi xem tập mới này.
- Bảng không kẻ ô, header sai chính tả, date/order đặc biệt và scan mờ vẫn có thể thiếu thông tin. Chữ OCR chưa đủ chắc phải rà soát; không tự suy ra quantity/model/HS để lấp chỗ trống.
- Các tỷ lệ trên là tập nhỏ được một người đối chiếu. Chưa có cơ sở công bố accuracy tổng quát hoặc F1 thực tế của toàn ZIP.

Kết quả và source hashes: `ZIP_ACCURACY_RESULTS.json`. Chi tiết before/after và cảnh báo theo tệp nằm trong `scratch/zip_corpus/`; manifest giữ archive SHA, member path, split và SHA từng nguồn.

## Kiểm thử / lưu nguồn

- `tests/test_zip_accuracy.py`: 6 regression tests dùng PDF/XLSX gốc từ ZIP, gồm 46 dòng qua hai trang, 9 cấu hình, pooled weights, Excel cells, OCR overlay và chặn container/header giả.
- `tests/test_zip_api.py`: original PDF → draft API → commit → load lại 9 SKU, kiểm source document ID/cell bbox và trạng thái unverified.
- `scratch/zip_final_targeted_tests.txt`: **7 pass** cho các kiểm tra ZIP/API mới.
- `scratch/zip_all_tests.txt`: **122 pass, 9 skip, 0 fail**; không tính skipped tests là pass.
- `scratch/zip_frontend_build.txt`: production build pass; `scratch/zip_frontend_tests.txt`: 2 frontend tests pass.
- Không sửa hồ sơ người dùng để thử nghiệm. Tests dùng DB tạm. Không tự duyệt HS.

## Dùng bản sửa

1. Khởi động lại app bằng `./run_local.sh` hoặc `.venv/bin/python serve.py` để dùng đúng môi trường có thư viện bảng mới. Đừng tiếp tục chạy process Python cũ đã nạp code trước sửa.
2. Với chứng từ đã tải trước, bấm nút **Trích xuất lại** trong danh sách chứng từ, chờ xử lý rồi chạy **Trích xuất & Tự điền**. Xác minh liên quan sẽ cần rà soát lại; dữ kiện không tự thành verified.
3. Xem nguồn/page/ô, đặc biệt ô gộp và những trường thiếu. Bản scan chưa nhận được hàng và bảng không kẻ ô cần người dùng bổ sung; không coi trường trống là chắc chắn tài liệu không có dữ liệu.

`HS_PDF_TABLES=0` tắt lớp ruled-cell extraction nếu cần so sánh fallback. Mặc định bật khi dependency có sẵn. Chính sách AI vẫn offline/disabled như trước.
