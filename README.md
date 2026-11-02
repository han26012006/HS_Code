# HS Workspace 2.0

Ứng dụng nâng cấp trực tiếp từ hs-assistant-app.zip của HSCode_AIProject. Giữ Python/FastAPI và lõi model; bổ sung giao diện React đóng gói sẵn, hồ sơ nhiều SKU, trích chứng từ theo trang và duyệt có căn cứ. Không phải bản model đã đạt HS8 >80%.

## Chạy ngay

Python 3.11 hoặc 3.12. Giải nén toàn bộ ZIP trước khi chạy.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python serve.py
```

Mở **http://127.0.0.1:8000**. Frontend đã build trong `web_dist`, không cần Node để dùng. Không cần chạy lại notebook 01–07 chỉ để mở ứng dụng. Các notebook vẫn dùng để xây dữ liệu, huấn luyện và đánh giá. Có thể dùng `run_windows.bat` hoặc `./run_local.sh`.

OCR scan cần cài Poppler + Tesseract + gói ngôn ngữ `vie` và `eng`. PDF có lớp chữ vẫn được đọc bằng pypdf khi chưa cài Poppler. PDF scan thiếu công cụ sẽ báo lỗi rõ; không tự coi là hồ sơ rỗng. Docker đã khai báo các công cụ này:

```bash
docker build -t hs-workspace .
docker run --rm -p 127.0.0.1:8000:8000 -v hs_workspace_data:/app/runtime hs-workspace
```

Dockerfile đã được soát nội dung; chưa chạy build image trong môi trường bàn giao này.

## Luồng nghiệp vụ

1. Tạo hồ sơ với ngày phân loại và luồng XNK. Thêm từng SKU.
2. Tải chứng từ; mở bản gốc cạnh văn bản trích theo trang/đơn vị. PDF không còn giới hạn 5 trang.
3. Bôi chọn đoạn trích để tạo thuộc tính. Người có nghiệp vụ kiểm tra số, đơn vị, thành phần, cơ chế trước khi xác minh.
4. Phân tích từ các thuộc tính đã xác minh. So sánh tối đa 3 dòng, đọc các dòng cùng HS6 và chú giải liên quan.
5. Ghi căn cứ: nguồn, trích đoạn, hỗ trợ/loại trừ/tham khảo, VN, AHTN2022, hiệu lực, người đối chiếu.
Nếu cần trích xuất lại sau khi sửa môi trường OCR, dùng nút mũi tên vòng trong cửa sổ chứng từ. Các thuộc tính/căn cứ liên quan được đưa về chờ kiểm tra, đồng thời kết quả và quyết định liên quan cần xem lại.

6. Lập phiếu duyệt hoặc yêu cầu bổ sung. Người duyệt khác người lập; hệ thống chặn thiếu thuộc tính, mâu thuẫn, phân tích cũ, nguồn chưa phù hợp hoặc hết hiệu lực.
7. Xuất PDF, Excel hoặc JSON. Thay đổi thuộc tính, căn cứ, SKU hoặc ngày phân loại yêu cầu xem lại kết quả và quyết định. Chạy lại phân tích cũng chuyển quyết định hiện tại sang lịch sử.

Tên người thao tác là thông tin tự khai trong không gian nội bộ, chưa có SSO, RBAC, chữ ký số hay kiểm chứng danh tính. Nhật ký có chuỗi hash nhưng người quản trị máy vẫn có thể sửa dữ liệu; không tuyên bố bất biến chống sửa.

## Nguồn dữ liệu đóng gói

- `data/catalogue.jsonl`: 11.414 dòng VN8 từ snapshot của dự án, bao gồm cấu trúc phân cấp. SHA/version hiện trong Cài đặt. Chưa đối chiếu tất cả với văn bản ký và sửa đổi tại thời điểm sử dụng.
- `data/legal_notes.json`: 102 phạm vi chú giải phần/chương từ corpus dự án; chưa xác nhận đầy đủ tính áp dụng hiện hành.
- `data/legal_sources.json`: registry nguồn TT85/2026, TT121/2025 và trạng thái bản sao QĐ117. Quy định quy trình không được biến thành nhãn mã HS.
- `data/demo_evidence.json`: 4 bản trích cần rà soát; nút mẫu tạo 2 hồ sơ thép/laser. Các thuộc tính đều CHƯA KIỂM TRA; mã quan sát không được dùng làm gold. Bản trích TXT không thay thế chứng từ PDF gốc, SHA gốc được ghi riêng.

Chứng từ thương mại dùng làm nguồn sự kiện/thuộc tính, không tự làm nhãn huấn luyện. Chưa đưa mọi archive người dùng gửi vào tập huấn luyện; chưa đủ cơ sở để tuyên bố đã tận dụng đầy đủ tất cả dữ liệu.

## Model

Mặc định: BM25 tra cứu danh mục, chạy CPU và không cần API. Đây là baseline, chưa phải bộ máy thực thi đủ GRI/Notes.

Model ranker của notebook 02:

```bash
python -m pip install -r requirements-model.txt
# Linux / macOS
export HS_BASE=/path/to/HSCode_AIProject
export HS_ART=/path/to/HSCode_AIProject/03_MoHinh/artifacts_v4
python serve.py
```

PowerShell dùng `$env:HS_ART="C:\...\03_MoHinh\artifacts_v4"`. Nếu chưa tái tạo v4, có thể chủ động trỏ `HS_ART` tới `artifacts` cũ; đây là nhánh legacy chưa đạt kiểm chứng mới. **Không trộn ranker/embedding/index giữa hai phiên bản.** Manifest v4 được kiểm tra hash trước nạp. Lõi dùng tiền lệ train, không dùng valid/test làm ví dụ mặc định. Không nạp `final.json` cũ trừ khi có freeze đúng manifest; không đổi sang baseline âm thầm khi model lỗi.

Ứng dụng không chứa encoder/trọng số vài GB. Chuẩn bị cache model đúng phiên bản trước; model chỉ được nạp khi chọn phương pháp. `HS_MODEL_ALLOW_DOWNLOAD=1` cho phép tải encoder khi người vận hành chủ động cấu hình. Điểm ranker, softmax và confidence HS4 không hiển thị thành xác suất đúng HS8.

Nhánh Qwen notebook 07: `requirements-qwen.txt`, CUDA/PyTorch phù hợp, cache `Qwen/Qwen3-4B-Instruct-2507` revision `cdbee75f17c01a7cc42f958dc650907174af0554`, `HS_ENABLE_QWEN=1`. Dùng prefill từng 256 token, không cắt đầu vào âm thầm. Nhánh này chưa chạy kiểm tra trên GPU thật ở bản bàn giao; lỗi VRAM được báo, không tự gọi API thay thế.

Nhánh OpenAI notebook 07: `requirements-openai.txt`, đặt `OPENAI_API_KEY` và `HS_ENABLE_OPENAI=1` trên máy chủ, sau đó xác nhận trong màn hình phân tích. Snapshot `gpt-5.4-mini-2026-03-17`; giới hạn mặc định 12 lượt / $0,50 ước tính, không phải cam kết hóa đơn. Không tự retry khi trạng thái phí chưa rõ. Cache theo đầu vào + cây ứng viên + phiên bản tránh gửi lặp. Không có lượt API trả phí thật nào được chạy trong quá trình nâng cấp này. Khóa không đặt vào browser hoặc ZIP.

Hai model chỉ dẫn dùng pool tối đa 200 mã BM25, full đường dẫn danh mục, schema và kiểm tra đoạn trích; có quyền từ chối thiếu dữ kiện. **Chưa đưa đủ chú giải, GRI và tiền lệ hiện hành vào suy luận tự động.** Đúng schema/citation không chứng minh phân loại đúng. Chưa nhánh nào được quảng bá là đạt >80%.

## Chức năng khác

Tra cứu mã và các dòng cùng HS6; đọc chú giải/nguồn pháp lý; rà soát CSV/XLSX tối đa 5.000 SKU với mô tả gần nhau và mã khác nhau. Tương đồng không chứng minh sai mã, không tự đổi danh mục. Mã CSV giữ dạng chuỗi và số 0 đầu. Báo cáo Excel giữ văn bản thành literal, không thực thi công thức do nội dung nguồn chèn vào.

Màn hình chất lượng tách số hồ sơ vận hành với kết quả lịch sử M0 32/109 (29,4%). Không dùng tỷ lệ duyệt để báo accuracy. Không có dữ liệu thuế suất/FTA/chống bán phá giá được xác minh để tính thuế hiện hành tự động. API `/api/v2/estimate` chỉ so sánh số do người dùng nhập, không dùng để chọn HS và không ước tính tiền phạt.

## Phát triển, kiểm thử và lưu dữ liệu

```bash
npm ci
npm run build
python -m pip install -r requirements-ci.txt
python -m pytest -q
```

Giữ `web_dist` cùng `api.py` khi bàn giao. `scripts/dev.mjs` cho môi trường phát triển hỗ trợ Python; môi trường Node-only không thể chạy backend Python. Bản Streamlit là màn hình hướng dẫn chuyển sang app mới; mã cũ ở `legacy` để đối chiếu, không phải giao diện được hỗ trợ.

Toàn bộ dữ liệu ứng dụng nằm trong `runtime` hoặc `HS_WORKSPACE`; sao lưu cả SQLite và `uploads`. Khi sao lưu đang chạy, dùng SQLite backup API hoặc dừng ứng dụng, không sao chép riêng một file SQLite trong lúc WAL còn đang ghi. Không thay đè runtime bằng bản ZIP mới. Model cache riêng và không được copy dữ liệu valid/test làm train.

Mặc định chỉ nghe 127.0.0.1. Nếu đưa lên mạng phải có HTTPS, xác thực/ủy quyền phù hợp, quản lý bí mật, chính sách truy cập/retention và sao lưu; `HS_API_KEY` hiện chỉ là khóa không gian chung. Chưa có khả năng cách ly tenant.

Xem `docs/REVIEW_BOARD_2026-11-01.md` và `docs/VALIDATION.md` để biết phát hiện, chức năng đã có và giới hạn kiểm chứng thực tế.


Bản2.1: thuế theo điều kiện và nguồn ô, lưu lịch sửSKU, tìm bằng chứngV5 cục bộ, bảngchấtlượngHS2/4/6/8. ĐọcHUONG_DAN_CHAY.md. Chưa chứng minh tăngaccuracy; không mởtựchốtHS8.
