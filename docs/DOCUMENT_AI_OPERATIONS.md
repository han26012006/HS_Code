# Vận hành Document AI

## Khởi chạy và cấu hình

Dùng requirements hiện có; không thêm OCR engine hoặc provider AI mới:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-ci.txt
python serve.py
```

Poppler cần có `pdftotext`, `pdftoppm`; OCR cần Tesseract. Kiểm tra:

```bash
pdftotext -v
pdftoppm -v
tesseract --list-langs
```

| Cấu hình | Mặc định / hành vi |
|---|---|
| `HS_WORKSPACE` | Root lưu case/document database; dùng đường dẫn riêng cho QA. |
| `HS_MAX_DOCUMENT_PAGES` | 500; vượt hạn mức báo lỗi rõ, không cắt ngầm. |
| `HS_MAX_UPLOAD_MB` | 128 / file. API tối đa 30 file / draft. |
| `HS_OCR_DPI` | 300; giới hạn 100–600 cho raster OCR; cấu hình sai xuất warning OCR. |
| `HS_TESSDATA_PREFIX` | Đường dẫn tessdata nếu cần; truyền cho Tesseract. |
| `HS_OCR_LAYOUT_TSV` | `0`; `1` bật aligned text từ word boxes của **cùng Tesseract**, chưa bật mặc định vì mới có paired synthetic scan experiment. |

Text layer có sẵn được giữ, không OCR chỉ vì trang ít chữ. Poppler lỗi sẽ thử pypdf; trang cần OCR nhưng thiếu công cụ được báo theo stage. Language chọn vie+eng nếu có, nếu không dùng ngôn ngữ sẵn có và vẫn yêu cầu rà soát.

Không xem status document `needs_review` hay fact `extracted` như đã được chuyên viên xác minh. Quotes phải đúng page/product/field; xem source header unit và cảnh báo multiline. Không dùng legal reference để tự điền product/transaction facts. HS declared có nguồn riêng, không phải mã đề xuất hoặc quyết định.

## Frontend

`frontend/src/main.jsx` và `frontend/public/assets/docfirst.js` là source. Không chỉ sửa bản trong web_dist. Production build đã được kiểm tra bằng Node 22.12.0, Vite 6.1.0 trong tác vụ này.

```bash
npm ci
npm run build
npm test
```

Build đưa public review script vào web_dist; không mất file như cơ chế hand-edit trước đây. UI giữ quy trình xem chứng từ → kiểm tra source/thiếu/mâu thuẫn → sửa value hoặc xác nhận matching → lưu. Đổi SKU label của người dùng không xóa model nguồn. Giao dịch và source fields có thể xem lại sau reload.

## AI-assisted extraction

Mặc định **không có provider và không có outbound AI request**. `assisted_extraction.py` chỉ là abstraction layer có mock tests. Không có environment flag nào tự biến nó thành Vision LLM hoạt động.

Khi phát triển một provider thật, phải truyền policy `enabled=True`, `allow_external_data=True`, page/token/cost budgets và authorization theo request. Provider phải có estimate trước invocation. Mọi suggestion giữ unverified/needs_review, phải resolve đúng document/page/block/quote và field permission. Không tự gắn suggestion vào SKU hoặc bật phân loại HS; cần product ownership review và eval độc lập trước khi đưa vào pipeline mặc định.

Không đo quality của LLM bằng mock tests. Không gửi chứng từ ra ngoài để “thử xem” khi chưa được phép.

## Regression và benchmark

Repo có `pytest.py` compatibility shim: dùng **console entrypoint `pytest`**, tránh `python -m pytest` ở root bị import nhầm shim.

```bash
pytest -q tests
pytest -q tests/test_document_ai_generalization.py tests/test_extraction_safety.py tests/test_document_first.py tests/test_autofill_api.py
python scripts/benchmark_document_ai.py --fixtures tests/fixtures/document_ai/development.json --output /tmp/development_after.json
python scripts/benchmark_document_ai.py --fixtures tests/fixtures/document_ai/reserved_synthetic.json --output /tmp/reserved_after.json
python scripts/benchmark_document_ai.py --fixtures tests/fixtures/document_ai/adversarial_development.json --output /tmp/adversarial_after.json
python scripts/benchmark_document_ai.py --fixtures tests/fixtures/document_ai/development.json --backend scratch/document_ai_before --output /tmp/development_before.json
python scripts/evaluate_ocr_layout.py
```

Giữ cùng fixture/evaluator hashes khi so sánh. Baseline chỉ giữ những module cần chạy benchmark, không dùng làm phiên bản production. Các tỷ lệ synthetic chỉ áp dụng evaluation mask đã gán nhãn. `table_row_exact_precision=null` nghĩa không có row predictions để tính precision. Source-grounding rate không phải human hallucination rate.

Browser E2E được lưu tại `scratch/document_ai_browser_e2e.cjs`; đường dẫn Chrome/Node trong script là cấu hình máy kiểm thử. Chạy server QA với `HS_WORKSPACE` riêng và port riêng, không dùng DB người dùng cho fixtures. Script file manifest nằm ở `scratch/document_ai_browser_files.json`. Xem browser result JSON và screenshots để kiểm tra review/reload.

## Gán nhãn thực tế và holdout

```bash
python scripts/document_ai_annotations.py --database runtime/workspace.sqlite --output /tmp/review_queue.json
python scripts/document_ai_annotations.py --validate /tmp/review_queue.json
```

Validation của queue chưa review phải thất bại; không đổi pending thành reviewed chỉ để sinh accuracy. Người có nghiệp vụ cần:

1. Gán document kind, shipment/group và template family trước khi chia tập. Tránh cùng lô/template/duplicate SHA đi vào cả development và holdout.
2. Gán product IDs và membership theo dòng/section, ghi cả no-match/ambiguous/conflicting; không chỉ gán positive model matches.
3. Gán field/value, exact document/page/quote; table rows/cells, units và các trường thực sự missing. Kiểm tra PDF/ảnh gốc, không chỉ text cache.
4. Hai reviewer khác nhau rà soát và xử lý bất đồng. Giữ source SHA và reviewer identity.
5. Các mẫu đã dùng để thiết kế parser nằm trong `real_development_exposure.json`, không được coi là real holdout. Reserved synthetic cũng không phải holdout độc lập.
6. Chỉ sau khi annotations được duyệt mới chuyển thành benchmark ground truth; chưa có reviewed real corpus nên không công bố real accuracy. Báo denominator, split/group hashes, precision/recall/F1, matching negatives, citation/product ownership và human unsupported-value assessment riêng.

Queue chứa nội dung chứng từ người dùng, chỉ lưu và rà soát trong môi trường được phép; công cụ không upload queue ra ngoài.
