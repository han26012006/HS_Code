# HS Workspace 2.5.0 · Kiểm toán dữ liệu và xếp hạng

Ngày 04/11/2026. Phạm vi là pipeline Việt Nam/AHTN 2022. Giữ nguyên ảnh chụp và chỉ số 2.4.0 để đối chiếu.

## Quyết định sản phẩm

Có thể thử nội bộ quy trình đối chiếu có người duyệt. Model chưa đạt điều kiện tự chọn HS8 hoặc tự ghi tờ khai. Bản này sửa việc dùng chứng từ sai SKU và nối quy trình đánh giá với đúng engine mà app phục vụ. Kết quả đối chứng không chọn được trọng số mới để thay M0. Guided của 2.4.0 tiếp tục phục vụ truy hồi.

## Nguồn và chất lượng nhãn

- Sổ bao phủ khóa theo SHA-256 có 966 tệp, gồm 605 tệp được nhận và 361 tệp không vào benchmark. Trong các lý do loại, 191 tệp thuộc phiên bản cũ cần đối chiếu chính xác và 158 tệp thiếu mã hợp lệ hiện hành. Các lý do có thể trùng nhau. Không ghép mã cũ theo tiền tố hoặc tự bù số.
- Có 26 hồ sơ có mã OCR thuộc danh mục và chỉ bị loại bởi giới hạn tập đóng băng. Danh sách nằm trong `v2_5/DATA_AUDIT.json`. Chúng cần xác minh chứng từ, kết luận, vòng đời và nhóm trước khi dùng cho snapshot mới. Có 0 nhãn được đánh dấu là chuyên gia thẩm định.
- Kiểm tra toàn bộ 605 PDF không có SHA-256 trùng. Không phát hiện mã HS8 đích hiện nguyên dạng trong mô tả bằng phép dò đã ghi. Phép dò không bắt được diễn giải, lỗi OCR hoặc tín hiệu gián tiếp.
- Thông báo 8976/TB-CHQ ghi **39072990** ở trang 3. Cache trước đây có **39072900**. OCR V4 hiện đã đọc đúng và tệp vẫn ở ngoài cohort. Đối chiếu này xác minh mã được công bố, không xác minh phân loại cho SKU khác. Hai thông báo 354 và 977 khớp snapshot. Chi tiết, nguồn và SHA của bản quét Drive ở `v2_5/OFFICIAL_SOURCE_REVIEW.json`.
- Bổ sung nguồn chính thức cho TT86/2026/TT-BTC và hai văn bản hợp nhất 73, 74/2026/VBHN-TT-BCT vào thư viện. Đây là nguồn đối chiếu phạm vi nghiệp vụ. Không dùng làm nhãn HS8 hoặc bảng thuế suất. Metadata hiệu lực TT121/2025 được đối chiếu trên Cổng Chính phủ và liên kết với mẫu thông báo, thay thế và hủy.
- Chưa lấy được tập kết luận sau 21/09/2026 đủ bản gốc, chứng từ kỹ thuật và nhãn thẩm định độc lập. Hàng chờ của 2.4.0 vẫn giữ riêng.

Nguồn chính thức

- [Thông báo 8976/TB-CHQ, trang 3](https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2025/6/16/VB_8976.pdf#page=3)
- [Thông tư 121/2025/TT-BTC](https://vanban.chinhphu.vn/?docid=216623&pageid=27160)
- [Thông tư 86/2026/TT-BTC](https://vanban.chinhphu.vn/?docid=218821&pageid=27160)
- [Văn bản hợp nhất 73/2026/VBHN-TT-BCT](https://vanban.chinhphu.vn/?docid=219509&pageid=27160) và [74/2026/VBHN-TT-BCT](https://vanban.chinhphu.vn/?docid=219510&pageid=27160)

## Ảnh hưởng của chia tập và đối chứng xếp hạng

Tách thời gian trong 605 hồ sơ có thứ tự. Audit nối nhóm doanh nghiệp, SHA của PDF và cặp mô tả gần nhau bằng cosine TF-IDF ký tự với ngưỡng 0,90. Có 28 ca test nối với tập sớm hơn. Thêm một ca thiếu nhóm, lát cắt test thận trọng còn 65/94. Trong đó 44 ca có mã chưa gặp khi train. Đây là lát cắt phân tích độ nhạy, vẫn dùng dữ liệu lịch sử đã được xem. Nhóm doanh nghiệp trùng hoặc văn bản gần nhau chưa đủ để kết luận cùng SKU.

| Phương pháp | HS8 Top 1 validation (97) | HS8 Top 1 test (94) | HS8 Top 1 lát cắt test (65) |
|---|---:|---:|---:|
| M0 | 23 | 24 | 12 |
| Pairwise logistic HS8 | 13 | — | — |
| Pairwise logistic có phân cấp | 17 | — | — |
| Histogram gradient boosting | 18 | — | — |
| Hợp hạng pairwise HS8 với M0 | 23 | 22 | 11 |
| Hợp hạng pairwise phân cấp với M0 | 23 | — | — |

Cố định đúng Top 200 của M0 cho tất cả phương pháp. Giữ nguyên tiêu chí chọn trước khi đọc feature test. Challenger tốt nhất theo Top 1 validation hòa M0 nhưng giảm HS4 Top 3 từ 66 xuống 55. Trên test lịch sử, challenger sửa 1 ca và làm hỏng 3 ca. M0 Top 1 vẫn bằng 0 trên 51 ca mã chưa gặp. Trên lát cắt 65, danh sách M0 chứa mã tham chiếu ở 45 ca, song chỉ đứng đầu ở 12 ca. Cần cùng lúc cải thiện cả bằng chứng để tìm mã và khả năng phân biệt những mã đã tìm được.

Thử nghiệm dùng lại 15 đặc trưng đã lưu. Kết quả nói về các mô hình và đặc trưng đã thử, không kết luận cross-encoder hoặc mô hình tài liệu sẽ thất bại. Artifact sklearn của M0 được lưu bằng 1.6.1, thử nghiệm chạy trên 1.8.0. Top 10 của M0 đã được kiểm tra từng ca với bản dự đoán lưu. Kết quả không được dùng để mở auto-approve.

## App và quy trình đánh giá thật

Bản 2.5.0 chặn dùng tệp riêng của SKU B để xác minh thuộc tính hoặc làm căn cứ của SKU A. Tệp dùng chung cấp hồ sơ vẫn dùng được. Liên kết sai phạm vi có từ bản cũ được báo và loại khỏi lần phân tích hoặc duyệt mới. Lịch sử và ảnh chụp quyết định cũ được giữ lại để kiểm toán. Tệp cùng checksum đã gắn riêng cho một SKU không tự đổi phạm vi vì được tải lên lần nữa.

Notebook 12 chạy audit, sổ bao phủ và đối chứng reranker CPU, không đụng tới snapshot. Với hồ sơ mới, dùng `pilot_eval.py` theo thứ tự:

1. **freeze** khóa các nhóm đã gặp, hồ sơ và thuộc tính theo nguồn, phiên bản app và checksum dữ liệu. Giữ nhãn ở kho riêng. Chọn ca có đủ thông tin và ca cần yêu cầu bổ sung.
2. **predict** chạy BM25 và Guided qua đúng `InferenceService` với thuộc tính đã xác minh. Lưu shortlist, nhóm HS4, trạng thái yêu cầu bổ sung, thời gian và checksum. Không cần mở tệp nhãn.
3. **score** mở nhãn được hai người thẩm định độc lập, cần người thứ ba xử lý bất đồng. Kiểm tra checksum rồi chấm Top 30, Top 3 HS4, thứ hạng đầu và xử lý thiếu thông tin. Đã thử kỹ thuật bằng ca giả lập. Chưa có phép đo năng lực trên dữ liệu mới.

Hồ sơ pilot mới tách theo doanh nghiệp, nhóm sản phẩm và thời gian. Nếu có thông báo sửa/hủy, nhập cùng chuỗi vào sổ nguồn. Nhóm chọn lại cấu hình cần tách riêng với nhóm dùng để hiệu chuẩn ngưỡng và kiểm thử cuối. Khi có đủ hồ sơ, thử cross-encoder đa ngôn ngữ hoặc reranker LLM có chứng cứ theo điều khoản trên một danh sách ứng viên cố định. Dùng cùng chứng từ và cùng ngân sách ứng viên cho các model. [HSCodeComp (ACL 2026)](https://aclanthology.org/2026.acl-long.937/) là tài liệu tham khảo thiết kế bài kiểm tra phân cấp. Nhãn mã 10 số của benchmark đó không được dùng làm nhãn VN8.
