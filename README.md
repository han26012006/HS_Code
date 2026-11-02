# HS Workspace 2.2

Hỗ trợ quyết định mã HS và lưu bằng chứng cho từng SKU tại Việt Nam. Bản nâng cấp từ `hs-assistant-app.zip` trong HSCode_AIProject, đối chiếu ngày 02/11/2026.

## Chạy ứng dụng

Python 3.11 hoặc 3.12. Giải nén toàn bộ gói trước khi chạy.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python serve.py
```

Mở `http://127.0.0.1:8000`. Giao diện đã build trong `web_dist`; không cần Node hoặc chạy lại notebook 01–07 để mở app. Mặc định chạy BM25 trên danh mục, không tải model hay gọi API trả phí.

OCR scan cần Poppler, Tesseract và gói ngôn ngữ `vie`/`eng`. PDF có lớp chữ vẫn đọc được khi chưa cài OCR. Bản Docker đã khai báo các công cụ OCR; dữ liệu cần volume bền vững.

## Quy trình được hỗ trợ

1. Tạo hồ sơ, SKU; ghi ngày phân loại và ngày đăng ký tờ khai khi đã biết.
2. Tải chứng từ; kiểm tra thuộc tính theo đúng trang/đơn vị. Chỉ dữ kiện đã xác minh đi vào phân tích.
3. Tạo danh sách đối chiếu; đọc các nhóm khác nhau, chú giải và tiền lệ Việt Nam. Khi thiếu thông tin hoặc model từ chối, danh sách truy hồi được ghi rõ là tham khảo.
4. So sánh 2–3 mã theo cùng ngày, luồng XNK và trị giá. Thuế suất/chính sách cần người đối chiếu ghi căn cứ. Chưa biết chính sách vẫn là **chưa biết**. So sánh không chọn mã có thuế thấp và không đo xác suất bị kiểm tra.
5. Ghi nguồn hỗ trợ/loại trừ và mã/phạm vi áp dụng. Căn cứ mâu thuẫn phải có xử lý được lưu vết trước khi duyệt.
6. Người duyệt khác người lập; nêu một mã khác đã xem xét và lý do loại. Duyệt tạo bản chụp dữ kiện, phân tích, căn cứ, đoạn trích, người duyệt và phiên bản nguồn.
7. Xuất PDF/XLSX/JSON hoặc **ZIP bằng chứng**, gồm bản gốc đã tải vào hồ sơ và manifest SHA256. Kiểm tra sao lưu và phục hồi riêng.

## Ba phần mới trong 2.2

| Phần | Hành vi | Giới hạn |
|---|---|---|
| So sánh hệ quả | Lưu kịch bản theo phiên bản SKU/phân tích; chênh thuế XNK bằng Decimal; chính sách và điều kiện FTA được ghi riêng | Chưa tự xác minh thuế hiện hành; chưa phải tổng nghĩa vụ thuế hay expected loss |
| Căn cứ Việt Nam, hỏi bổ sung | Tra cứu 798 bản trích OCR, mặc định chỉ train, loại nguồn sau ngày hồ sơ; cảnh báo tuổi thông báo; phân biệt từ chối và truy hồi | Chưa chứng nhận hiệu lực hoặc áp dụng pháp lý của tiền lệ; chưa có accuracy mới |
| Hồ sơ tại lúc duyệt | Bản chụp có hash, lịch sử xử lý mâu thuẫn, phạm vi mã, đối chiếu phương án khác, ZIP giữ bản gốc | Hash không phải chữ ký số; tên người duyệt tự khai; URL/đoạn trích chưa thay thế bản gốc chưa tải |

Mốc lưu tham chiếu 5 năm tính từ **ngày đăng ký tờ khai**, không từ ngày AI chạy. Có cờ tiếp tục giữ khi kiểm tra/tranh chấp; không tự xóa. Nghĩa vụ kế toán, thuế và quy định khác có thể dài hơn.

## Nguồn và Chương 98

Snapshot workbook ngày 05/04/2026 được đọc lại cả 39 sheet: **11.414 mã thông thường**, **586 dòng Chương 98 / 457 mã khác nhau**. Giữ mọi dòng Chương 98 trong `data/tax/chapter98_snapshot.jsonl`; cột I là mã tham chiếu quan sát, không phải đơn vị tính. Chức năng tính từ Chương 98 bị chặn để người nghiệp vụ kiểm tra điều kiện riêng.

Biểu tổng hợp không tự xác nhận toàn bộ mức thuế tháng 11/2026. Ký hiệu `*`, nhiều mức VAT, RCEP, thuế tuyệt đối/hỗn hợp và phòng vệ thương mại cần kiểm tra điều kiện. So sánh hệ quả chỉ tính thuế XNK theo tỷ lệ phần trăm đã đối chiếu; màn hình kịch bản thuế riêng hỗ trợ thêm VAT và khoản thuế do người dùng nhập.

Registry ghi NĐ169/2026 từ 01/07/2026; NĐ128/2020 hết khoảng hiệu lực đã ghi từ ngày đó. Luật 11/2026/QH16 có hiệu lực **01/03/2027**, chưa áp dụng sớm vào 02/11/2026. Đây là registry có ngày đối chiếu, chưa phải hệ thống theo dõi tự động mọi thay đổi pháp luật.

## Model và bằng chứng thực nghiệm

M0 lịch sử: HS8 Top-1 **32/109 = 29,4%**; stack cũ **27/109 = 24,8%**. Tập test đã được xem trong phát triển và nhãn còn tạm thời. 16 cấu hình CPU của dự án giữ M0 theo gate VALID; thay đổi app không tạo ra một accuracy mới.

Điểm truy hồi, softmax và HS4 confidence không phải xác suất đúng HS8 đã hiệu chuẩn. Không tự chốt mã, không dùng phiếu duyệt làm nhãn gold. Bộ ba nhóm trong UI là các tiền tố khác nhau từ danh sách HS8 truy hồi, không đồng nhất với Top-3 của một model HS4 riêng.

Nhánh model dự án, Qwen và OpenAI vẫn là tùy chọn. Xem `HUONG_DAN_CHAY.md` về `HS_ART`, cache model và biến môi trường. API ngoài mặc định tắt; nhánh OpenAI cần xác nhận gửi thuộc tính cho từng lượt. Không có inference GPU hoặc API trả phí thật trong lần nâng cấp 2.2.

## Nâng cấp và vận hành

Giữ nguyên thư mục `runtime` hoặc đường dẫn `HS_WORKSPACE` hiện có. Bản 2.2 tự thêm cột/bảng, không xây lại dữ liệu. Căn cứ cũ chưa gắn mã/phạm vi phải được đối chiếu bổ sung trước lần duyệt mới. Quyết định cũ chưa có bản chụp vẫn nằm trong lịch sử, không tự tạo bản chụp hồi tố.

Sao lưu toàn bộ SQLite và `uploads`. Khi app đang ghi WAL, dùng SQLite backup API hoặc dừng app trước khi sao lưu; thử phục hồi. Gói ZIP hồ sơ là bản xuất, không thay thế bản sao lưu vận hành.

Mặc định chỉ nghe 127.0.0.1. Chưa có SSO, chữ ký số, RBAC hay cách ly tenant. `HS_API_KEY` là khóa chung; tên hai người khác nhau chưa chứng minh hai danh tính khác nhau. Bản này phục vụ demo và pilot có người nghiệp vụ giám sát.

## Kiểm thử và tài liệu

```bash
python -m pip install -r requirements-ci.txt
python -m pytest -q
npm ci
npm test
npm run build
```

Đọc `docs/REVIEW_BOARD_2026-11-02.md` để xem phản biện chín góc nhìn, đối chiếu pháp lý/nghiên cứu, ma trận tính năng và kế hoạch kiểm định. `docs/VALIDATION_V2_2.json` ghi kiểm tra thực tế cùng phần chưa chạy.
