# Document-first: báo cáo sửa nguyên nhân gốc
> Báo cáo lịch sử của lần sửa trước. PDF kỹ thuật hiện đã có lại; acceptance mới đã chạy trên hai PDF gốc và Chrome. Xem [báo cáo nâng cấp](DOCUMENT_AI_GENERALIZATION_REPORT.md).


Ngày kiểm tra: 04/11/2026. Không sửa/xóa các thay đổi có sẵn của người dùng. Không tự phê duyệt HS.

## Nguyên nhân đã kiểm chứng

Đã trace `api.py` → `AutoFillDraftManager` → parsing/type detection/extraction → hai frontend → commit/apply → `Workspace.add_fact` → load lại.

1. **Không có loại legal reference.** `DocumentTypeDetector.detect` trước sửa chỉ chấm điểm các loại chứng từ thương mại/kỹ thuật. Mọi tài liệu đều đi vào `InformationExtractor.extract_candidate_skus`. Nay kiểm tra vai trò theo nội dung tại `extractor.py:295`, `product_extraction.py:15`; loại pháp lý không cấp dữ liệu sản phẩm/giao dịch.
2. **Gộp dữ liệu và first-match.** Nhánh generic cũ trong `extract_candidate_skus` tạo `combined_text` từ toàn bộ tài liệu, có pattern nhận `danh mục hàng hóa xuất khẩu, nhập khẩu` làm tên; `_extract_observed_hs(combined_text)` nhận mã đầu tiên. Vật liệu/cấu tạo có thể lấy từ tài liệu khác nhưng gắn `name_doc_id`/`name_p_num`. Nhánh này đã được thay hoàn toàn bằng `extractor.py:513` → `product_extraction.extract`.
3. **Dữ liệu giả mang nhãn trích xuất.** Code cũ sinh model `DEMO-DRY-{num}`, mã HS mặc định `85163100`, `72193300`, `90182000`, mô tả cấu tạo/công dụng không có trong nguồn; generic còn điền vật liệu phù hợp công năng, sản xuất theo quy chuẩn và hàng mới 100%. Đã bỏ các nhánh hardcode; chỉ nhận giá trị nguồn trực tiếp. Không dùng tên/nhóm hàng để kết luận HS.
4. **Frontend thực sự được serve có logic khác React source.** `web_dist/index.html` tải `assets/docfirst.js`. Trong `openReviewWorkspaceModal`, dòng 362 trước sửa fallback số tờ khai sang invoice/document number, giải thích chính xác việc điền `31/2022/TT-BTC`; đoạn sau tự tạo SKU khi rỗng, tự điền hàng mới 100%, coi `fact.quote` có nội dung là nguồn hợp lệ. Đã sửa file được serve và React source. Ngày phân loại không còn lấy ngày invoice trong frontend được serve.
5. **Ghép SKU không an toàn và đối chiếu nhầm sản phẩm.** `extract_for_case` trước sửa nhận tên chứa nhau hoặc chỉ có một SKU là cùng sản phẩm. `CrossDocumentReconciler` đối chiếu mọi công suất ở mọi tài liệu, gây mâu thuẫn giả cho hai model. Nay ghép model chính xác, bản ghi chưa rõ danh tính giữ riêng và cần rà soát; đối chiếu công suất trong cùng entity.
6. **Save có thể mất nguồn một cách im lặng.** Commit upload rồi thêm fact trước khi đảm bảo có pages, bắt lỗi rồi chuyển fact thành `manual_declaration`; apply bắt lỗi rồi bỏ qua. Nay process trước khi lưu, kiểm tra document/page/quote/field/SKU, lỗi trả ra rõ, rollback các bản ghi của case mới khi commit lỗi. Không xóa tệp content-addressed dùng chung trong rollback.
7. **Confidence không có cơ sở hiệu chuẩn.** Tỷ lệ score + hằng số trước đây không phải xác suất. Nay trả `null`; giữ key để tương thích.

Không tìm thấy giới hạn cắt ngầm trong vòng lặp PDF của hai đường parsing. `DocumentService.process` có giới hạn trang được cấu hình và báo lỗi rõ khi vượt. Có lỗi decode bytes PDF thành văn bản khi parser thất bại trong auto-fill: đã thay bằng trang rỗng có lỗi cần rà soát. Không xác nhận được bug lấy ngày hiện tại làm ngày chứng từ; ngày hiện tại là mặc định hệ thống cho ngày phân loại.

## Thay đổi

- `hs_assistant/product_extraction.py`: `role`, `segments`, `extract`, chuẩn hóa Unicode/khoảng trắng; tách theo trang/section/dòng bảng, ghép model, giữ riêng bản ghi thiếu model, giữ evidence trực tiếp, đánh dấu thiếu/mâu thuẫn.
- `hs_assistant/extractor.py`: `parse_file_bytes`, `DocumentTypeDetector.detect`, `InformationExtractor.extract_dossier_fields`, `extract_candidate_skus`, `_make_field`; `CrossDocumentReconciler.reconcile`; `AutoFillDraftManager.create_draft`, `update_draft`, `_validate_reviewed_sources`, `commit_draft`, `extract_for_case`, `apply_to_case`.
- `hs_assistant/documents.py`: `DocumentService.process` dùng chung bộ phân loại nội dung.
- `api.py`: lỗi validation PATCH/apply trả 422; không đổi tên API.
- `frontend/src/main.jsx`: giữ số tờ khai riêng, trạng thái user input, loại legal và cảnh báo thiếu dữ liệu.
- `web_dist/assets/docfirst.js`: sửa các fallback thực sự đang được serve, nguồn/trang, không tạo SKU/hàng mới giả; incremental apply gửi đúng SKU/facts; điều hướng dùng ID case API trả về.
- Tests: thêm `test_extraction_safety.py`, `test_autofill_api.py`; chỉnh ba fixture/assertion cũ để yêu cầu model rõ và không yêu cầu confidence giả.

Schema DB và public API giữ nguyên. Field status cũ `unverified/conflict/verified` được giữ cho workflow duyệt; `extraction_status` biểu diễn `extracted/conflicting`, `missing_fields` biểu diễn thiếu. Các alias `source_document_id/source_page/source_quote/field_name/sku_id` được bổ sung trong draft. Giá trị chỉnh sửa được phân biệt `user_input`, lưu bằng source kind `manual_declaration` hiện có; dữ liệu tự trích xuất lưu nguồn `document`, luôn cần người kiểm tra. Origin/declared-code evidence được giữ riêng trong draft, không trở thành kết luận HS.

## Kết quả mẫu thực tế

Xem `DOCUMENT_FIRST_ACTUAL_RESULT.json`.

- Có bản PDF pháp lý thật, đã parse đủ **103 trang**.
- PDF kỹ thuật gốc đã mất khỏi đường dẫn lưu trong DB và không tìm thấy trong Downloads/attachments. DB còn nguyên hai trang text đã trích xuất; kiểm tra dùng các trang này, **không tuyên bố chạy lại OCR/PDF kỹ thuật gốc**.
- Hai SKU `DEMO-DRY-1200`, `DEMO-DRY-1600`, cùng tên `Máy sấy tóc cầm tay gia dụng, dùng điện.`
- Công dụng, cấu tạo, thông số và đóng gói lấy nguyên nội dung nguồn. Điện áp 220 V, tần số 50 Hz, công suất tương ứng 1200 W / 1600 W. Toàn bộ fact SKU thứ nhất trỏ trang 1, SKU thứ hai trang 2.
- HS khai báo trống; số tờ khai trống; không sinh SKU từ pháp luật; không lấy `85071010`, `31/2022/TT-BTC` hay “khởi động” làm dữ kiện sản phẩm.
- Chưa có căn cứ về số tờ khai, invoice, xuất xứ, vật liệu, tình trạng hàng và quy trình sản xuất: không tự điền.

## Kiểm thử và giới hạn

- `scratch/final_extraction_results.txt`: **21 pass** trên code cuối cùng; bộ regression extraction/document-first/API, gồm phân trang, nhiều model, dòng invoice dạng bảng, invoice + packing cùng SKU, đổi thứ tự, tên giống nhau thiếu model, thiếu số tờ khai, sai trang/nguồn, parse lỗi, xung đột giao dịch, rollback, commit/reload/apply.
- `scratch/extraction_pytest_results.txt`: bộ mở rộng workspace/API/decision support: 74 pass, 3 skip (thiếu model artifacts / rank_bm25).
- `scratch/full_regression_results.txt`: **93 pass, 9 skip** khi chạy toàn bộ suite; các test bỏ qua cần model artifacts/rank_bm25 không có trong môi trường. Sau các thay đổi validation cuối cùng, chạy lại 21 test extraction/API liên quan và đều pass.
- `scratch/frontend_render_results.txt`: syntax + render smoke test file JavaScript thực sự được serve, với output mẫu thật: đúng hai model/công suất/trang; input rỗng vẫn 0 SKU. Dùng DOM stub, chưa phải browser end-to-end.
- Không có `npm`/Node CLI trong PATH nên chưa build React/Vite hoặc chạy `npm test`. Frontend file được serve được sửa trực tiếp và kiểm tra qua Node runtime có sẵn của công cụ.
- Bộ trích xuất bảo thủ, dựa vào nhãn/section/header và identity rõ. Layout không nhận dạng hoặc OCR kém phải người dùng rà soát, không có đảm bảo đọc mọi kiểu bảng. Chưa kiểm tra lại PDF kỹ thuật gốc hoặc chất lượng OCR của bản gốc. Cần khôi phục file để hoàn tất acceptance test hai PDF upload từ đầu qua browser.
