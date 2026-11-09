# Kiểm toán từ dữ liệu đến sản phẩm HS Workspace 2.4.0

Ngày 04/11/2026 · Nhóm 8 · Việt Nam

## Quyết định

Có thể triển khai thí điểm nội bộ cho tra cứu, so sánh hệ quả và duyệt hồ sơ có căn cứ. Chưa đủ bằng chứng cho chức năng tự quyết định HS8. Chất lượng nghiệp vụ cần đo trên quy trình người duyệt, kết quả đối chiếu và hồ sơ hoàn chỉnh. Chất lượng model cần đo riêng trên tập hồ sơ có nhãn kiểm chứng.

## Ba nguyên nhân có dữ liệu đối chứng

1. **Độ phủ nhãn huấn luyện thấp.** 414 thông báo train phủ 211/11.414 mã, trong đó 140 mã chỉ có một thông báo. Ở test, 51/94 ca có mã chưa xuất hiện trong train, M0 đúng Top 1 ở 0/51 ca này. Trong 43 ca mã đã gặp, M0 đúng 24 ca. Đây là khác biệt quan sát được, có thể đồng thời chịu ảnh hưởng của nhóm hàng và mô tả.
2. **Lỗi truy hồi và xếp hạng cùng tồn tại.** M0 trên test có 21/94 ca thiếu mã ở Top 200 và 49/94 ca có mã trong Top 200 nhưng không xếp đầu. Hybrid 06 giảm số thiếu từ 21 xuống 13, nhưng cấu hình giữ mười mã đầu của M0 nên Top 1 vẫn 24/94. Trần oracle của bộ ứng viên không phải tỷ lệ chính xác dự báo.
3. **Dữ liệu đánh giá khác đầu vào sản phẩm.** Các mẫu là văn bản thông báo đã OCR, có phần mô tả do cơ quan xử lý trình bày. Hồ sơ vận hành đi từ chứng từ, thuộc tính đã xác minh và tình huống thiếu thông tin. Tập test lịch sử đã được xem trong phát triển. Có 19 ca test và 14 ca validation thuộc nhóm doanh nghiệp đã gặp trong train. Các nhãn đều tạm, kể cả nhãn được ghi là đối chiếu thủ công đồng thuận. Chưa có hai chuyên gia độc lập duyệt theo hồ sơ.

## Kết quả đối chứng

| So sánh | Validation | Test lịch sử | Phạm vi |
|---|---:|---:|---|
| M0 HS8 Top 1 | 23/97 | 24/94 | Notebook 02 |
| M0 Top 200 → pool kết hợp 06 Top 200 | 79 → 88/97 | 73 → 81/94 | Giữ Top 10 M0 |
| Guided v1 → v2, Recall@30 | 42 → 61/97 | 42 → 54/94 | Cùng mô tả lưu trữ |
| Guided v1 → v2, HS8 Top 1 | 6 → 9/97 | 11 → 14/94 | Cùng mô tả lưu trữ |
| Guided v1 → v2, HS4 Top 3 | 47 → 54/97 | 46 → 47/94 | Ba nhóm khác nhau xuất hiện trước trong danh sách HS8 |
| Guided v1 → v2, Recall@30 trên mã chưa gặp | 12 → 19/51 | 15 → 16/51 | Mã chưa gặp ở cấp HS8 |
| Pool 07 → Guided v2, Recall@30 | 67 → 61/97 | — | Cùng chuỗi đầu vào đã tiền xử lý, cùng K=30 |
| 09 OpenAI + M0 dự phòng, HS8 Top 1 | 45/97 | — | Pool nghiên cứu 200 mã, 40/85 ngoài pilot, không đo trên app |

Một số model nhìn thấy đúng mã nhưng vẫn chọn sai. Lượt 09 chấp nhận 90 đầu ra và đúng 42/90 trong số đó. Vì vậy tỷ lệ trả lời cao chưa phải tiêu chí đủ để đưa model vào quy trình tự động. 08 chọn giữ M0. Kết quả 05 mới nhất kiểm tra được trên Drive chỉ có giao thức, nên chưa dùng để xếp hạng model.

## Thay đổi đã triển khai và cách tái lập

- `hs_assistant/retrieval_experiment.py` thêm TF-IDF từ/cụm hai từ cho mô tả danh mục và tiền lệ, chuẩn hóa nhiễu văn bản và hợp nhất theo thứ hạng. Tiền lệ chỉ có trước ngày phân loại. Chọn cấu hình trên validation, giữ một đối chứng BM25 và một đối chứng Guided v1. Sau đó xem test lịch sử cho cấu hình đã chốt.
- `docs/evaluation/benchmark_guided_v2.py` xuất giao thức, quyết định chọn và số đếm. `audit_corpus_and_bridge.py` đối chiếu với pool 07 trên cùng truy vấn. Nhật ký `v2_4/` ghi đủ mẫu số và checksum nguồn. Ở K=30, Guided v2 tìm thêm 5 ca pool 07 bỏ sót và bỏ sót 11 ca mà 07 tìm thấy. Hợp hai pool có oracle 72/97 trước giới hạn 30, nên cần thuật toán hợp nhất và kiểm thử để nói có cải thiện.
- Đã ghi quan hệ 638/TB-TCHQ thay 5523/TB-TCHQ theo [PDF Hải quan, trang 5](https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2025/2/14/TB.638.pdf#page=5). Sổ sửa nguồn chỉ có quan hệ đã đối chiếu. Không dùng 638 để bổ sung nhãn train vì đây là hồ sơ cùng dòng thông báo và cần kiểm soát trùng nhóm.
- Mốc AHTN 2022 theo [Bộ Tài chính về TT72/2022](https://mof.gov.vn/phap-luat-tai-chinh/van-ban-moi/mofucm260556). Hồ sơ trước mốc yêu cầu danh mục phiên bản khác. Bản Luật 11/2026/QH16 trong thư viện theo [Cổng văn bản Chính phủ](https://vanban.chinhphu.vn/?classid=0&docid=219299&pageid=27160), có hiệu lực 01/03/2027.
- Đối chiếu ngoài dự án có thể dùng [HSCodeComp, ACL 2026](https://aclanthology.org/2026.acl-long.937/) để thiết kế ca kiểm thử thuộc tính và quy tắc theo cấp. Benchmark đó dùng mã 10 số và bộ hồ sơ riêng. Không gộp nhãn với VN8. [WCO Explanatory Notes](https://www.wcoomd.org/en/topics/nomenclature/instrument-and-tools/tools-to-assist-with-the-classification-in-the-hs/explanatory-notes.aspx) dùng theo quyền truy cập phù hợp.

## Chạy gì tiếp

1. **Chạy 11** để tái lập kết quả trên snapshot đang dùng. Có thể chạy riêng 05 nếu cần hoàn tất LambdaRank. Kiểm tra `test_diagnostic.json` và giao thức khớp SHA trước khi dùng kết quả. Chạy lại 01 chỉ khi đầu vào, OCR hoặc nguồn nhãn thay đổi, rồi chạy 06 → 02 → 03 với cùng manifest.
2. **Chốt tập mới trước khi xem nhãn.** Lấy hồ sơ sau 21/09/2026, có chứng từ và thuộc tính kỹ thuật, chia theo nhóm sản phẩm, doanh nghiệp và chuỗi văn bản đính chính. Giữ riêng dữ liệu huấn luyện, hiệu chỉnh và future test. Hai người phân loại độc lập, người thứ ba xử lý bất đồng. Cho phép nhãn “cần thêm thông tin”. `prospective_eval.py` kiểm tra cohort đóng băng và chấm kết quả sau duyệt. Sổ chờ lấy bản gốc ở `v2_4/source_intake.json`.
3. **Thử model mới trên cùng pool trước.** Cố định ứng viên và bản chú giải theo ngày. So bộ xếp hạng đơn giản với cross-encoder đa ngôn ngữ và LLM buộc trích điều kiện phân biệt. Đo kết quả riêng trên mã chưa gặp, độ phủ khi từ chối, tỷ lệ gợi ý sai trong ca thiếu dữ liệu, p95 và chi phí. Nếu Recall@30 còn thấp, cải thiện nguồn và truy hồi trước khi tối ưu reranker. Dùng biến thể 09 làm đối chứng trong nghiên cứu.
4. **Đo thí điểm có người duyệt.** Trước khi mở rộng, đo thời gian hoàn thành hồ sơ, số lần phải bổ sung chứng từ, lỗi nghiêm trọng lọt qua khâu duyệt và khả năng tái lập căn cứ. Đặt trước biên chấp nhận theo từng nhóm hàng và so với workflow thủ công trên cùng hồ sơ. Mọi nhánh vẫn lưu quyết định nội bộ và bắt buộc người duyệt.

Các phép đo ở đây dùng CPU và artifact đã lưu. Chưa huấn luyện lại BGE hoặc gọi OpenAI mới. Không có kết quả prospective VN8 hoặc chứng nhận toàn bộ biểu thuế, FTA và chính sách chuyên ngành.
