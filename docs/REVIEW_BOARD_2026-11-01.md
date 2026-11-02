Ghi chú phiên bản: tài liệu này ghi nhận bản 2.0. Với bản 2.1, xem HUONG_DAN_CHAY.md và TEST_RESULTS_V5.json; phần thuế theo kịch bản và tra cứu kho V5 đã được bổ sung.

# Đánh giá dự án và phạm vi bàn giao HS Workspace 2.0

Ngày đối chiếu: 01/11/2026. Đây là phân tích theo 10 góc nhìn, không phải chứng nhận của một hội đồng chuyên gia đã ký thẩm định. Nguồn gồm code/artefact dự án đã kiểm tra, chứng từ mới và các nguồn công khai dẫn cuối báo cáo.

## Kết luận cần dùng để quyết định

Chưa có bằng chứng HS8 đạt 80%. Việc thay giao diện hoặc thêm LLM không tạo ra bằng chứng đó. Bản bàn giao phù hợp cho thử nghiệm có người nghiệp vụ kiểm tra từng SKU; chưa phù hợp tự động chốt mã để khai báo. Giá trị MVP là giảm công gom hồ sơ, đối chiếu thuộc tính, tìm ứng viên và lưu lý do quyết định.

Kết quả lịch sử M0 là 32/109 = 29,4% HS8 Top-1; stack cũ 27/109 = 24,8% trên test dù valid tăng. Các nhãn còn tạm thời và test cũ đã được xem trong các vòng phát triển nên không thể gọi là kiểm chứng độc lập. Chưa thực hiện lại toàn bộ 01–07 trên corpus hoàn chỉnh sau các sửa lỗi. Không báo một accuracy mới cho bản ứng dụng.

## Bằng chứng lỗi và nguyên nhân

| Phát hiện từ audit dự án | Hệ quả | Xử lý trong code bàn giao |
|---|---|---|
| 798 case tạm gán nhãn; train 580, valid 109, test 109; 57/109 nhãn test không thấy ở train | Classifier chỉ dự đoán nhãn đã học bị giới hạn. 47,7% là trần của nhánh chỉ có nhãn train trên tập này, không phải trần mọi phương pháp | Tra cứu toàn bộ danh mục, không khóa ứng viên vào nhãn train; model chỉ dẫn dùng pool tối đa 200 mã |
| OCR cũ chỉ đọc đầu tài liệu; app cũ chỉ 5 trang, đầu vào còn cắt ký tự | Có thể mất thông số, thành phần hoặc điều khoản loại trừ | Đọc mọi trang trong giới hạn tài nguyên công khai; giữ trang, phương pháp, hash, tiến độ, lỗi; không cắt âm thầm |
| Nhãn thủ công chưa đủ provenance, có sửa mã theo khoảng cách ký tự | Nhãn sai làm sai cả train/eval và khiến kết quả khó diễn giải | Không sửa nhãn như vậy trong app, không biến mã quan sát và phiếu duyệt thành gold |
| App dùng tiền lệ từ mọi split, tự nạp stack cũ | Nguy cơ leakage và đưa nhánh kém hơn vào sử dụng | Mặc định chỉ tiền lệ train; freeze/manifest phù hợp mới dùng cấu hình final |
| Điểm ranker / HS4 được diễn giải như độ tin cậy HS8 | Người dùng có thể tin quá mức vào mã sai | Không hiển thị % confidence HS8 khi chưa calibration; luôn bước duyệt |
| 84 tệp chứng từ trích xuất, 401 trang PDF trong audit bổ sung; 0 nhãn gold mới được xác minh | Nhiều tài liệu hơn chưa đồng nghĩa nhiều ví dụ đúng hơn | Chứng từ là nguồn thuộc tính/căn cứ. Bộ mẫu giữ pending, tách mã quan sát |

Các con số trên là kết quả audit corpus lịch sử, không phải số chứng từ đã được người dùng tải vào SQLite của ứng dụng mới. 38 tệp thương mại có ledger truy cập không chứng minh mọi archive đã được đưa vào huấn luyện.

## Đánh giá từ 10 góc nhìn

| Góc nhìn | Phán đoán và quyết định triển khai |
|---|---|
| 1. Nghiệp vụ XNK/Hải quan | Đơn vị quyết định là SKU tại thời điểm giao dịch; một bộ chứng từ có thể có nhiều dòng hàng và nhiều mã. App tạo hồ sơ → từng SKU → nguồn → thuộc tính → đối chiếu → duyệt. Chưa tự nộp tờ khai hoặc gửi yêu cầu tới cơ quan Hải quan. |
| 2. Chuyên môn phân loại HS | Tên giống nhau chưa đủ để chọn mã. Cần xét mô tả dòng, cấu trúc, GRI, chú giải, bản chất và tình trạng khi XNK. Thép cần vật liệu, chế tạo, kích thước; feed cần thành phần/quy trình; laser cần cơ chế/công dụng. App cho đọc cấu trúc, chú giải và ghi vai trò nguồn; chưa phải engine thực thi đầy đủ 6 GRI. |
| 3. Tuân thủ Việt Nam | Khóa phạm vi VN/AHTN2022 và ngày phân loại. TT85/2026 được nguồn Chính phủ ghi hiệu lực 15/09/2026; bản ký TT85 và Công báo TT121 được đóng gói. Không coi quy trình là đáp án mã. Nguồn Mỹ/Trung Quốc chỉ là benchmark ngoại miền, không ánh xạ tùy tiện sang VN8. Chưa xác minh tất cả sửa đổi về sau của mọi văn bản. |
| 4. Research reviewer | Chưa đủ điều kiện tuyên bố novelty hoặc chất lượng Q1. Hybrid retrieval, LLM rerank và giao diện không tự là đóng góp nghiên cứu mới. Đóng góp có thể kiểm chứng là bộ SKU VN được thẩm định, benchmark theo thời gian, thí nghiệm thu thập thuộc tính và risk/coverage có provenance. Cần ablation, baseline cạnh tranh, code/data version và đánh giá độc lập. |
| 5. Kiến trúc AI | Giữ BM25 làm đối chứng rẻ, deterministic. Ranker dự án, Qwen 4B và OpenAI là các nhánh lựa chọn riêng. Không tự chuyển sang API nếu GPU lỗi. Cần đo recall@K trước khi kết luận reranker yếu; mã đúng ngoài pool thì model xếp hạng lại không thể sửa. |
| 6. Product | Người dùng đầu tiên là người khai/nhân viên phân loại và người duyệt nội bộ. Pain point: thiếu thông tin hàng, chứng từ phân tán, khó tái hiện quyết định. Khác biệt nên kiểm chứng là thời gian xử lý và khả năng audit theo SKU; không phải tuyên bố AI chính xác hơn VNTR/tra cứu Hải quan/hscode.pro. Chưa có khảo sát adoption hoặc ROI thực tế. |
| 7. Phương pháp nghiên cứu | Đăng ký trước giả thuyết, biến độc lập và split. Tách SKU tương tự, nhà sản xuất, notice thay thế/đính chính và bản dịch cùng case khỏi các split khác nhau. Chốt valid rồi mới mở test mới. Bootstrap theo nhóm hàng, báo CI và McNemar trên cùng cohort phù hợp; không chọn model bằng test cũ. |
| 8. Ground truth | Mã trên tờ khai, invoice, OCR hay draft không mặc định đúng. Cần nhãn được chuyên gia phân loại độc lập đối chiếu, hồ sơ kỹ thuật tương ứng và nguồn kết luận có trạng thái hiệu lực. Tách claim, observed code, proposed code, internal decision và adjudicated gold. |
| 9. Red team | Thử mã trong phần loại trừ, đơn vị mm/cm, ngưỡng kích thước, lẫn tên/thông số, thông báo bị hủy, thay phiên bản HS, OCR thiếu bảng, prompt injection và SKU gần trùng khác mã. App kiểm tra nguồn trích, date/version và revision; chưa chứng minh chống mọi tấn công hoặc nhận biết mọi mâu thuẫn ngữ nghĩa. |
| 10. Responsible AI | Không tự chốt, không bịa confidence, không tự thăng hạng nhãn người dùng thành gold. Khóa API ở server, dữ liệu lưu local, API ngoài mặc định tắt. Tên người duyệt tự khai; chưa có xác minh danh tính, RBAC, tenant isolation, retention tự động hay audit log chống quản trị viên sửa. |

## Sản phẩm có gì, mức hoàn thành nào

| Chức năng | Trạng thái trong bản code này |
|---|---|
| Giao diện tiếng Việt, sidebar, dashboard, quản lý hồ sơ và nhiều SKU | Đã code, frontend build thành công; dashboard đã kiểm tra bố cục trên trình duyệt |
| Tải PDF/ảnh/Word/Excel/CSV/TXT, ZIP/RAR, hash và chống đường dẫn thoát gói | Đã code; ZIP/path và trích nguồn được integration test. RAR chưa có fixture thực tế chạy trong bản app này |
| OCR mọi trang và đối chiếu theo trang/đơn vị | Đã test PDF 7 trang và ảnh OCR thực với số/đơn vị; chưa benchmark OCR tiếng Việt trên toàn bộ chứng từ thật |
| Tạo thuộc tính từ đoạn người dùng chọn, verified/unverified/conflict | Đã code và test API, chưa hoàn tất kiểm thử click toàn luồng browser |
| BM25 toàn danh mục, model ranker, so sánh 3 mã, xem dòng cùng HS6 | BM25 đã chạy test; adapter ranker có code, chưa nạp toàn trọng số BGE trong lượt bàn giao |
| Qwen 07 và OpenAI 07 với từ chối, schema, quote check, cache và giới hạn API | Đã tích hợp. Consent/cache/validation test bằng stub; chưa inference GPU thật hoặc gọi API trả phí |
| Chú giải và nguồn chính thức | 102 phạm vi chú giải; 2 PDF chính thức đóng gói có SHA; cần người nghiệp vụ đánh giá áp dụng |
| Duyệt nội bộ với căn cứ, người đối chiếu và bảo vệ revision | Đã test thành công và các tình huống chặn; chưa thay thế chữ ký hoặc quyết định Hải quan |
| Xuất PDF/XLSX/JSON và lịch sử | Đã test API; PDF tiếng Việt đã render kiểm tra. JSON có toàn lịch sử; Excel có lịch sử quyết định, nguồn và mã literal |
| Rà soát danh mục doanh nghiệp | Đã test giữ mã 0 đầu, cặp gần giống khác mã, mã chưa có trong danh mục; không tự sửa |
| Thuế, FTA, phòng vệ thương mại, rủi ro phạt | Chưa có nguồn rate/scope hiện hành được xác minh đầy đủ; không đưa tính thuế tự động vào UI |
| Tra cứu ruling tự cập nhật, e-customs, SSO, SaaS nhiều tenant | Chưa triển khai |

## Làm gì để tăng accuracy có cơ sở

Không có model hay tập dữ liệu free nào bảo đảm đạt 80% VN8 cho cohort chưa biết. Ưu tiên thí nghiệm theo thứ tự sau, dừng nhánh không có gain trên valid.

| Thí nghiệm | So sánh công bằng cần chạy | Điều kiện kết luận |
|---|---|---|
| Thuộc tính thay vì OCR thô | Cùng SKU, cùng split; OCR thô vs thuộc tính đã xác minh; đo lỗi OCR theo số/đơn vị | Chứng minh chất lượng thông tin đầu vào tạo gain, không đưa HS hoặc nhãn vào đầu vào |
| Truy hồi danh mục và tiền lệ | BM25, char TF-IDF, dense, hybrid; cùng danh mục và train-only precedent | Đo recall@20/50/200, unseen-code recall, thời gian và RAM trước rerank |
| Rerank có cấu trúc | Baseline mạnh nhất vs ranker vs instruction model, cùng pool | Không đổi test/nhãn khi thấy kết quả; kiểm tra hard negatives cùng HS6 |
| Điều kiện phân loại có thể kiểm chứng | Người chuyên môn viết predicate từ nguyên bản cho một nhóm hẹp; test ngưỡng, đơn vị và loại trừ | Không dùng LLM tự sinh luật rồi coi là đúng. Predicate chỉ lọc khi đủ bằng chứng |
| Hỏi bổ sung | Model từ chối khi thiếu thuộc tính → bổ sung câu trả lời được kiểm tra → chạy lại | Báo gain cùng chi phí câu hỏi và thời gian; không tính chỉ các case dễ còn lại |
| Fine-tune / metric learning / GNN | Chỉ sau khi có đủ nhãn VN8, group split và prototype toàn danh mục | KBGAT hoặc model lớn là challenger, không mặc định ưu việt; không lấy số paper làm số dự án |
| Từ chối và human-in-the-loop | Đặt threshold trên calibration riêng; frozen test mới | Báo cả accuracy toàn bộ và selective accuracy/coverage. 90% trên 10% mẫu không tương đương 90% toàn bộ |

Mục tiêu 80% cần định nghĩa là HS8 Top-1 trên cohort VN8 độc lập, đầy đủ hồ sơ và được thẩm định. Ngưỡng tin cậy, coverage và các nhóm hàng trọng yếu cần chốt trước. Nếu muốn chứng minh mức tối thiểu 80% với độ tin cậy thống kê, không chỉ nhìn point estimate 80%; phải thiết kế cỡ mẫu và kiểm tra cận dưới CI phù hợp. Chưa có căn cứ đưa ngày lịch chắc chắn hoàn thành model.

## Dữ liệu cần bổ sung: ưu tiên và vai trò

1. **SKU trong doanh nghiệp + hồ sơ kỹ thuật đúng mã hàng/đúng lô + nhãn được thẩm định.** Thu thập thành phần/COA, nguyên lý/datasheet, công đoạn sản xuất, tình trạng hàng và kích thước. Đây là phần quyết định còn thiếu; không thể thay bằng PDF quy trình chung.
2. **Thông báo xác định trước, phân loại, đính chính, thay thế/hủy và hồ sơ kỹ thuật liên quan.** Lấy từ cổng Hải quan/nguồn văn bản chính thức; TVPL là nguồn phát hiện/bản sao, cần đối chiếu bản ký và trạng thái. Theo dõi linked notice lifecycle, không đếm bản thay thế như mẫu độc lập.
3. **Danh mục, GRI, chú giải, biểu thuế và nguồn quy định có phiên bản.** Dùng làm knowledge/rule evidence. Không suy ra hàng hóa có nhãn đúng chỉ vì mã xuất hiện trong nguồn.
4. **Datasheet nhà sản xuất miễn phí.** Là technical evidence khi đối chiếu đúng model/SKU; không tự chứng minh mã HS8 VN. Catalogue chung, brochure marketing và sản phẩm cùng tên nhưng cấu hình khác chỉ là tham khảo.
5. **HSCodeComp / CROSS / ATLAS.** Dùng benchmark riêng theo đúng jurisdiction và số chữ số; kiểm tra giấy phép, trùng lặp và phạm vi. Người dùng đã chạy HSCodeComp/CROSS nên tải lại chúng không tạo thêm thông tin mới. ATLAS có nguồn CROSS nên phải kiểm tra trùng trước khi gọi là dữ liệu bổ sung.

Không trộn miễn phí tải về với quyền tái phân phối hoặc huấn luyện thương mại. Cần lưu license, URL, ngày tải, SHA, đơn vị hồ sơ và quyết định thẩm định. Hồ sơ app xuất JSON có provenance nhưng `approved_decisions_are_training_gold=false`.

## Đọc nghiên cứu để tránh lựa chọn model theo cảm tính

- **HSCodeComp, ACL 2026:** 632 sản phẩm, 32 danh mục, mã 10 chữ số; tác giả báo khoảng cách đáng kể giữa agent và chuyên gia. Bài nhấn mạnh áp dụng quy tắc phân cấp và lỗi suy luận dài. Điều này ủng hộ kiểm thử thực tế thay vì hứa model lớn sẽ tự đạt 80% VN8. Không chuyển kết quả benchmark đó thành accuracy dự án.
- **ATLAS, arXiv 2025:** benchmark lấy từ CROSS của Mỹ, có fine-tune LLaMA-3.3-70B. Đó là preprint về HTS Hoa Kỳ, không phải ground truth VN8 hay một nguồn độc lập hoàn toàn với CROSS.
- **Attribute knowledge & KBGAT, Scientific Reports 2025:** mô hình hóa quan hệ thuộc tính khai báo thành graph và làm ablation. Đây là hướng thử nghiệm có cơ sở cho structured attributes; chưa chứng minh chuyển miền sang corpus nhỏ/nhãn tạm thời này. Không nên dựng GNN trước khi sửa nhãn, split và baseline.

## Nghiệm thu sản phẩm và ROI

Cho người lập hồ sơ và người duyệt xử lý cùng các case đã được thẩm định trong thiết kế crossover, cân bằng thứ tự. Đo thời gian trung vị/SKU, tỷ lệ cần hỏi lại, số nguồn mở, độ đầy đủ chứng cứ, số mã sai sau duyệt, tỷ lệ sửa gợi ý sai của AI và mức phụ thuộc AI. Chi phí gồm OCR, inference, duyệt và bảo trì pháp lý. Chưa có số để báo ROI hoặc tiết kiệm phần trăm.

Chỉ cân nhắc pilot giới hạn khi nghiệp vụ kiểm tra nguyên bản và mọi quyết định có người chịu trách nhiệm. Phát hành tự động cần bằng chứng chất lượng riêng, bảo mật/ủy quyền phù hợp và vận hành nguồn cập nhật. Các kiểm thử phần mềm đính kèm không phải bằng chứng accuracy phân loại.

## Nguồn kiểm tra công khai

- Cổng Chính phủ, **85/2026/TT-BTC**, metadata và bản ký: https://vanban.chinhphu.vn/?docid=218770&pageid=27160
- Công báo, **121/2025/TT-BTC**, bản PDF chính thức: https://congbaocdn.chinhphu.vn/180507251028987904/2026/1/29/cong-bao-so-60-ngay-27-01-46958signed-1769648620477270334287.pdf
- Lan et al., **HSCodeComp**, ACL 2026: https://aclanthology.org/2026.acl-long.937/
- Yuvraj & Devarakonda, **ATLAS**, arXiv 2509.18400: https://arxiv.org/abs/2509.18400
- Qi et al., **Attribute knowledge and KBGAT**, Scientific Reports 2025: https://www.nature.com/articles/s41598-025-16580-7
- OpenAI, model snapshot/capabilities/pricing, đối chiếu 01/11/2026: https://developers.openai.com/api/docs/models/gpt-5.4-mini

Báo cáo không khẳng định đây là danh sách đầy đủ mọi luật, sửa đổi hay paper đến 01/11/2026. Không có chuyên gia Hải quan thật ký xác nhận cho các SKU mẫu trong bản bàn giao.
