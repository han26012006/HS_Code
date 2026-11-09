# HS Workspace 2.3.0 · Kiểm toán và phạm vi pilot

**Quyết định phát hành.** Chạy pilot hỗ trợ phân loại và lưu hồ sơ với người duyệt. Chưa bật tự chốt HS8. Luồng mới là một phương pháp tùy chọn. Chạy mặc định bằng BM25; không đưa kết quả Notebook 09 sang runtime vì đầu vào và danh sách ứng viên khác nhau.

## Chẩn đoán theo tầng

| Nguồn bằng chứng | Phát hiện | Quyết định |
|---|---|---|
| 01, 03 · Snapshot OCR và mẫu số | Legacy và V4 có 798 và 605 hồ sơ. Cùng 94 PDF test giữ nguyên nhãn, 43/94 mã đầu thay đổi, HS8 đi từ 26 xuống 24. Chênh lệch đồng thời gồm OCR, làm sạch và tập train 580 → 414. | Giữ checksum và mẫu số theo cohort. Muốn đo riêng OCR phải khóa tập train/test, nhãn, truy vấn đầu vào và cấu hình model. |
| 02, 05 · Baseline M0 và CPU | M0 giữ cổng chọn nhiều tầng. LambdaRank chạy lại đạt 22/94 test so với M0 24/94. | Không thay M0 bằng model phức tạp hơn chỉ vì đã huấn luyện được. |
| 04 · OCR kho chứng từ | Kho chứng từ phục vụ bằng chứng và tra cứu. Các chứng từ, trích đoạn và mã đã khai chưa tạo nhãn HS8 độc lập. | Lấy thuộc tính có nguồn và giữ hồ sơ nguyên bản. Nhãn độc lập cần hai chuyên viên và phân xử. |
| 06, 08 · Danh sách ứng viên | Kết hợp 06 và M0 có mã trong Top 200 ở 81/94 test. 08 nâng độ phủ validation 79 → 88 trên 97 ca. Reranker logistic, LambdaRank và blend không qua cổng chọn. | Dùng nhiều kênh để tăng độ phủ, đo riêng năng lực chọn mã. |
| 07, 09 · Qwen và GPT | Qwen hybrid giảm 3/12 → 1/12 sau fallback. GPT trên 97 validation tăng 23 → 45 đúng. Chấm ghép cặp cho thấy 28 sửa đúng và 6 làm sai từ ca M0 đúng. 39 gợi ý sai đã có mã đúng trong pool, 9 thiếu mã trong pool, 4 fallback sai. | Gợi ý qua bộ kiểm tra cú pháp vẫn có thể sai. Tiếp tục GPT làm đối chứng nghiên cứu. Thu thập thuộc tính phân biệt và kiểm điều kiện nhóm/phân nhóm trước khi thử bộ chấm cặp. |
| App 2.3.0 · Phát lại code truy hồi | Trên 94 mô tả lưu trữ, BM25 → guided: HS8 Top-1 0 → 11, Top 30 chứa mã 23 → 42, Top 200 chứa mã 41 → 68, Top 3 nhóm HS4 41 → 46. | App cung cấp chế độ truy hồi mới có giải thích tín hiệu. Chỉ số chưa đo trên thuộc tính đã xác minh qua giao diện. |

## Vận hành và nguồn

- Nhập chứng từ và xác minh các thuộc tính cần để phân biệt. Chọn **Truy hồi kết hợp · có tham chiếu**. Chọn các mã cần so sánh, đối chiếu nguồn và điều kiện riêng. Kịch bản thuế và FTA phải có nguồn phù hợp, đủ điều kiện và thời điểm áp dụng.
- Người lập ghi lý do chọn và loại phương án. Người duyệt độc lập kiểm thuộc tính, căn cứ và hiệu lực. Xuất hồ sơ, bản chụp và kiểm manifest. Tên khai báo trong workspace chưa xác thực danh tính. SHA256 phục vụ kiểm toàn vẹn và sao lưu, không thay chữ ký số.
- Phụ lục II của Thông tư 31/2022/TT-BTC đã bổ sung PDF Công báo và sáu trang dẫn Quy tắc 1–6. PDF SHA256 `e54b9be03cdf897fb63f06596a939d519552d457b994bdb011593d7ae2dd89de`. Các tóm lược gắn trang 50, 53, 59, 69, 70, 74. Nguồn và phạm vi theo ngày cần kiểm tra trên từng hồ sơ. [Công báo 557–558](https://congbaocdn.chinhphu.vn/CongBaoCP/CongBao/2022/7/37448/41055-1-557-558.pdf)
- Gói đã có bản ký Thông tư 85/2026/TT-BTC về quy trình phân loại. Nguồn này cung cấp căn cứ quy trình, không sinh nhãn cho SKU. [Bản ký trên Cổng thông tin Chính phủ](https://vanban.chinhphu.vn/?docid=218770&pageid=27160)
- Chưa đủ dữ liệu độc lập để xác nhận thuế suất, giấy phép, độ đầy đủ SEN theo mọi nhóm và mọi ngày. Ghi thiếu căn cứ là trạng thái nghiệp vụ. Không tự điền giá trị thiếu.

## Tái lập

```bash
PYTHONPATH=. python docs/evaluation/benchmark_guided.py \
  --app . --artifact /path/to/artifacts_v4 --output ./runtime/guided-replay
```

Script chạy trên CPU và không gọi API. Snapshot cần `precedents.parquet` và `pipeline_manifest.json`. 8 công thức được chấm validation trước khi phát lại công thức chọn trên test lịch sử. Các JSON đi kèm là kết quả lần chạy đã kiểm tra.

## Tạo đánh giá độc lập

1. Sau ngày khóa model, lấy SKU mới có tài liệu đủ quyền sử dụng. Gom các biến thể cùng sản phẩm và nhà sản xuất để ngăn rò rỉ giữa các tập. Ghi cả ca mô tả thiếu. Danh sách nhóm từng dùng lưu một nhóm mỗi dòng.
2. Tạo `cases.jsonl` gồm `case_id`, `group_id`, `classification_date`, `facts`. Khóa bằng `prospective_eval.py freeze --cases ... --existing-groups ... --catalogue data/catalogue.jsonl --cutoff ... --output ...`. Lưu bản khóa trước khi xem đầu ra. Hai chuyên viên đọc chứng từ và danh mục riêng, giữ kín dự đoán.
3. Tạo `gold.jsonl` gồm `case_id` và `reviews` gồm hai phiếu. Mỗi phiếu có `reviewer`, `result` là HS8 hoặc `needs_information`, và `evidence_ref` là nguồn và trang. Khi bất đồng, thêm `adjudication` của người thứ ba theo cùng cấu trúc. Lưu dữ liệu tham chiếu ở chỗ phân quyền.
4. Tạo `predictions.jsonl` gồm `case_id`, tối đa 30 mã trong `candidates`, tối đa 3 nhóm `headings`, và `proposal` là mã hoặc null. Chạy `prospective_eval.py score --cases ... --catalogue ... --manifest ... --gold ... --predictions ... --output ...`. Script kiểm đủ ca, checksum, đồng thuận và đếm lỗi đề xuất khi thiếu thông tin. Việc hai chuyên viên chấm độc lập và nguồn thực sự đủ căn cứ cần được bảo đảm trong quy trình, ngoài phần kiểm cấu trúc của script.
5. So cùng hồ sơ với tra cứu thủ công, BM25 và guided. Trước khi mở test, chốt chỉ tiêu theo loại sai có hậu quả, thời gian lập hồ sơ kể cả duyệt và tỷ lệ hồ sơ đủ căn cứ. Báo riêng Recall@30, HS4 Top-3, HS8, tỷ lệ đề xuất, lỗi khi cần hỏi lại và chi phí. Nếu chọn thử GPT hoặc cross-encoder, dùng cùng pool và cùng tập, bổ sung cặp mã cùng HS6 dễ nhầm và căn cứ phân biệt đã xác minh. Giữ test độc lập cho lần đánh giá khóa cuối.

Kết quả GPT có trong [Notebook 09](https://colab.research.google.com/drive/1Ass8owYW8Ly-RIInSUrEr0SwiCO_9yH5) và [biên nhận validation](https://drive.google.com/drive/folders/1ZYkNSxXEdJRV2fzSLAYP25qhM3odeI6P). Không cần chạy lại OCR hoặc gọi lại 97 ca GPT để tái lập các tổng hợp đã lưu.
