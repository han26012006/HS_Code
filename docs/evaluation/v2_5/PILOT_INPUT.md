# Mẫu đầu vào pilot

Mỗi dòng JSON là một hồ sơ đã bỏ định danh. Dùng mã băm/ID nội bộ nhất quán cho doanh nghiệp và họ sản phẩm. Đăng ký trước các nhóm đã dùng ở những vòng trước. Mỗi thuộc tính có nguồn `source_ref` do nhóm kiểm tra, ví dụ mã chứng từ nội bộ và trang. Chỉ thuộc tính mang trạng thái `verified` đi vào engine. Các mẫu dưới đây giả lập.

```json
{"case_id":"P01","company_group":"ORG_NEW_01","product_group":"PRODUCT_NEW_01","classification_date":"2026-10-30","product_family":"general","facts":[{"field":"name","value":"Máy sấy tóc gia dụng","status":"verified","source_ref":"doc-a:p1"}]}
```

Hồ sơ chưa đủ thông tin vẫn được giữ. Tệp nhóm trước đây có hai mảng `company_groups` và `product_groups`. Mỗi nhãn tách riêng theo `case_id`, có `reviews` gồm hai mục `reviewer`, `result`, `evidence_ref`. `result` là chuỗi mã HS8 hoặc `needs_information`. Khi hai người bất đồng, thêm `adjudication` có cùng ba trường và người thứ ba.

Đứng ở thư mục gốc của app:

```bash
PYTHONPATH=. python docs/evaluation/pilot_eval.py freeze --app . --cases cases.jsonl --known known.json --cutoff 2026-09-21 --output manifest.json
PYTHONPATH=. python docs/evaluation/pilot_eval.py predict --app . --cases cases.jsonl --manifest manifest.json --prediction-dir predictions
PYTHONPATH=. python docs/evaluation/pilot_eval.py score --app . --cases cases.jsonl --manifest manifest.json --prediction-dir predictions --gold reviewed.jsonl --output score.json
```

Ghi thời điểm khóa vào nhật ký nhóm. Biên nhận SHA-256 phát hiện thay đổi so với tệp đã khóa. Biên nhận không chứng minh thời gian với bên thứ ba.
