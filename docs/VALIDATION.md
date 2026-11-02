Ghi chú phiên bản: tài liệu này ghi nhận bản 2.0. Với bản 2.1, xem HUONG_DAN_CHAY.md và TEST_RESULTS_V5.json; phần thuế theo kịch bản và tra cứu kho V5 đã được bổ sung.

# Kiểm chứng bản HS Workspace 2.0

Mốc kiểm tra: 01/11/2026. Đây là kiểm chứng phần mềm và định dạng xuất, không phải kiểm chứng accuracy HS8.

- Python: **35 passed, 8 skipped, 0 failed** (`python -m pytest -q`).
- JavaScript: **2 passed**, kiểm tra giữ nguyên ngày phân loại khi browser ở Mỹ/Hawaii và mặc định ngày nghiệp vụ theo Việt Nam (`npm test`).
- Frontend: build Vite thành công; `web_dist` đã đóng gói, không cần Node để chạy app.
- API thử nghiệm dùng SQLite/thư mục tạm độc lập. Không thay nhãn hoặc ghi các case kiểm thử thành nhãn gold.

## Các hành vi đã kiểm tra

Tạo case/SKU; chưa có model vẫn khởi động; thiếu thuộc tính thì từ chối phân tích; engine model lỗi không chuyển sang baseline âm thầm; chặn API ngoài thiếu consent; cache lặp đầu vào không gọi lại stub; từ chối mã/citation LLM ngoài nguồn; không có confidence HS8 giả.

Duyệt thành công khi đủ điều kiện; chặn thiếu thuộc tính, cùng người lập/người duyệt, căn cứ nước ngoài, sai nomenclature, bị hủy/thay thế, tương lai/hết hạn, thiếu ngày hiệu lực hoặc nguồn; trích đoạn sai case bị từ chối; đổi thuộc tính/ngày hoặc chạy lại phân tích khiến quyết định cần xem lại. Thuế/phạt cũ không tiếp tục được gọi tự động.

ZIP path traversal bị chặn; API private và file cần khóa nếu cấu hình HS_API_KEY; PDF 7 trang giữ đủ trang cuối; OCR ảnh thực giữ được số 2.95 và 1552, vẫn yêu cầu người kiểm tra; mã 0 đầu được giữ; dữ liệu Excel bắt đầu bằng công thức được lưu dạng literal.

Xuất PDF/XLSX/JSON qua API thành công. PDF tiếng Việt 2 trang đã render và xem; 8 sheet Excel đã import/render kiểm tra và đọc lại kiểu mã. Mẫu xuất kiểm tra là hồ sơ chưa được duyệt, vì vậy các sheet căn cứ, ứng viên, lịch sử duyệt có thể chỉ có header; đây không phải bộ kết quả model mới.

## Kiểm tra giao diện và giới hạn

Đã mở bản render tĩnh từ đúng component React và dữ liệu 2 hồ sơ mẫu thực trong SQLite; kiểm tra màn hình tổng quan, hồ sơ SKU trên desktop và khung rộng 390px. Ảnh ở `previews`. Phát hiện lỗi ngày 01/11/2026 hiện thành 31/10 ở browser nước ngoài, đã sửa và xác minh lại 01/11/2026.

Backend Python chạy được bằng TestClient. Môi trường xem thử Sites được cấp không có uvicorn và các thư viện Python của ứng dụng; do đó **chưa kiểm tra click toàn luồng giao diện với backend sống trong browser**. Bản render dùng để kiểm tra bố cục, không phải demo giả backend và không được dùng làm bằng chứng hoàn thành E2E.

Chưa build/run Docker; chưa chạy launcher Windows trên Windows; chưa test RAR thật ở app mới; chưa đo OCR tiếng Việt trên corpus sản xuất; chưa inference đầy đủ BGE/ranker với artifact thật; chưa chạy Qwen4B trên GPU thật; chưa gọi OpenAI trả phí. Chi phí API mới được kiểm tra bằng stub; không có hóa đơn thực phát sinh.

8 test artifact lịch sử được skip vì chưa đặt HS_ART tới artifact thật trong môi trường bàn giao, không được tính là test pass. Không có phép đo HS8 mới nào trong báo cáo này.

Chi tiết máy đọc: `TEST_RESULTS.json`, `test_results.xml`. Lệnh và các giới hạn phần mềm nằm trong README.

Trích xuất lại OCR được test thêm: mọi thuộc tính/căn cứ liên quan trở về trạng thái chờ kiểm tra và phân tích liên quan bị vô hiệu hóa.
