## Dữ liệu và pipeline
- **Chủ đề/corpus:** *Introduction to Computer Science* (OpenStax); 1 tài liệu PDF, `document_id=openstax-intro-cs`. Nguồn được khai báo: https://assets.openstax.org/oscms-prodcms/media/documents/Introduction_To_Computer_Science_-_WEB.pdf. Quyền tái phân phối **cần xác minh từ PDF/điều khoản OpenStax** trước khi public corpus.
- **Số trang:** manifest hiện tại khai báo **34 trang nội dung** (trang vật lý 19–40 và 49–60; PDF có 939 trang vật lý). Pipeline kiểm tra các trang được chọn không rỗng và đối chiếu evidence quote với văn bản trích xuất.
- **Chuẩn hóa và lỗi:** `load_pdf` trích xuất PDF, chuẩn hóa Unicode NFC và khoảng trắng; mỗi chunk giữ `document_id`, nguồn, trang và metadata. Quote q08 đã được sửa để khớp văn bản trích xuất từ trang 22. Log có cảnh báo hai trang đầu rỗng; đây không phải các trang nội dung được chọn trong manifest.
- **Embedding:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, chạy local trên CPU; **384 chiều**, cùng model cho A/B/C. Môi trường: Python 3.11.9, Sentence Transformers 6.3.0, PyTorch 2.15.0.
- **Vector store:** PostgreSQL 16.16 + pgvector extension 0.8.7; Python `pgvector` 0.5.1 và `psycopg` 3.3.8. Bảng `ingestion_chunks`, khóa chính `(strategy,chunk_id)`, cosine distance (`<=>`), truy xuất Top 3. Lệnh chạy:

```bash
python -m starter.src.run --manifest data/manifest.json --benchmark data/benchmark/questions.json --output results --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

- **Chi phí:** embedding chạy local nên không phát sinh chi phí API trong pipeline; không tính điện, phần cứng, Internet và thời gian nhân công.
- **Metadata:** `document_id`, `source`, `page` lưu ở các cột riêng; `category=computer_science`, `language=en` lưu trong JSONB từ manifest. **Hạn chế quan trọng:** JSONB không có `chapter`, trong khi một số câu hỏi lọc theo `chapter`; strategy C vì thế trả về rỗng cho một số câu hỏi lọc.

## Cấu hình và benchmark
- **A:** `fixed_size(size=500, overlap=50)`, không filter.
- **B:** `by_paragraph(max_size=500)`, không filter; đoạn dài hơn 500 vẫn bị cắt theo ký tự.
- **C:** chunking giống hệt B; thêm `metadata @> question.filter` nếu câu hỏi cung cấp filter. Đây là so sánh chỉ thay một yếu tố giữa B–C.
- **Benchmark:** 20 câu, 15 dev + 5 test (q01–q15 và q16–q20); có câu hỏi filter và gold evidence. `run.py` xác minh quote có trong trang nguồn sau chuẩn hóa trước khi đánh giá. Trên mỗi chiến lược, dùng cùng model, corpus, benchmark và truy xuất Top 3.
- **Tiêu chí lựa chọn:** ưu tiên Evidence Hit@3 trên **dev**, sau đó Hit@1 và chất lượng audit. Đây là tiêu chí dùng để diễn giải lựa chọn; **không có bằng chứng đã ghi lại tiêu chí trước khi xem test**, nên không khẳng định đã pre-register.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Ingest (s) | Chi phí API |
|---|---|---|---|---|---|---|
| A | dev | 7/15 (46.67%) | 11/15 (73.33%) | 251 | 50.604 | 0 USD |
| A | test | 3/5 (60.00%) | 3/5 (60.00%) | 251 | 50.604 | 0 USD |
| B | dev | 6/15 (40.00%) | 8/15 (53.33%) | 317 | 51.617 | 0 USD |
| B | test | 1/5 (20.00%) | 3/5 (60.00%) | 317 | 51.617 | 0 USD |
| C | dev | 5/15 (33.33%) | 7/15 (46.67%) | 317 | 37.251 | 0 USD |
| C | test | 1/5 (20.00%) | 1/5 (20.00%) | 317 | 37.251 | 0 USD |

*Embedding chạy local nên không phát sinh chi phí API; không tính điện, phần cứng, Internet hoặc thời gian nhân công. Số chunk và thời gian ingestion lấy từ `results/run_metadata.json`.*

### Manual Audit

| Strategy | Grounding/metadata score (5 câu, /10) | Coherence (10 trang) | Metadata/filter |
|---|---:|---|---|
| A | 8/10 | Chưa chấm (0/10 trang có điểm) | Chưa xác minh đầy đủ |
| B | 8/10 | Chưa chấm (0/10 trang có điểm) | Chưa xác minh đầy đủ |
| C | 4/10 | Chưa chấm (0/10 trang có điểm) | `chapter` thiếu; q17/q19 không có kết quả |

Điểm grounding/metadata là tổng năm nhãn `score_0_to_2` hiện có trong `results/manual_audit_reviewed.csv` cho mỗi strategy; đây là nhãn đã ghi, không phải đánh giá độc lập bổ sung. Trong file này có 15 dòng grounding đã chấm và 30 dòng coherence (10 trang × 3 strategy) **chưa có điểm**. Các trường `metadata_correct` và `filter_compliant` chưa được xác minh đầy đủ, vì vậy không kết luận metadata/filter audit đã hoàn tất.

Đã xuất toàn bộ **885 chunk** vào `results/audit_chunks.csv` (A: 251, B: 317, C: 317). Đây là dữ liệu để kiểm tra, không có nghĩa 885 chunk đã được đọc/audit thủ công. Các trang coherence đang được liệt kê trong file reviewed là trang 19–28; cần chấm các chunk tương ứng, đồng thời quyết định phạm vi audit theo yêu cầu môn học.

**Tệp minh chứng:** `results/metrics.csv`, `results/run_metadata.json`, `results/retrieval_traces.json`, `results/audit_chunks.csv`, `results/manual_audit_template.csv` và `results/manual_audit_reviewed.csv`.

## Phân tích và kết luận

- **A–B:** A hơn B trên dev: Hit@1 46,67% so với 40%; Hit@3 73,33% so với 53,33%. Khác biệt chính là fixed-size có overlap so với paragraph-based. Kết quả không đủ để chứng minh mọi corpus đều phù hợp fixed-size.
- **B–C:** B và C có cùng chunking, khác metadata filter. C giảm Dev Hit@3 từ 53,33% xuống 46,67% và Test Hit@3 từ 60% xuống 20%. JSONB chỉ có `category` và `language`, không có `chapter`; audit ghi nhận q17/q19 của C không trả kết quả. Đây là vấn đề cấu hình metadata của thử nghiệm này, không phải bằng chứng rằng lọc metadata luôn kém.
- **Ví dụ sai 1 — q16 (test):** hỏi sự khác biệt giữa machine learning và quy tắc thủ công. Strategy A trả về trang 35, 31, 60 nhưng không có `evidence_hit` trong Top 3; B/C cũng không hit. Có thông tin liên quan đến ML nhưng chưa trúng gold evidence.
- **Ví dụ sai 2 — q20 (test):** hỏi biểu diễn trực quan các bước thuật toán. Strategy A trả về trang 53, 20 và một chunk khác nhưng không chứa đủ gold evidence trong Top 3; B/C cũng không hit. Truy xuất theo ngữ nghĩa gần chưa đủ đảm bảo chứa bằng chứng cụ thể.
- **Chiến lược được chọn:** **A**, dựa trên Hit@3 dev cao nhất (11/15) và Hit@1 test 3/5; phù hợp làm baseline cho corpus/benchmark hiện tại. Đánh đổi là fixed-size có thể cắt giữa câu, cần kiểm chứng coherence.
- **Hạn chế:** chỉ một PDF, 20 câu và 5 câu test; kết quả phụ thuộc gold evidence và cách chia chunk. Coherence audit chưa được chấm; metadata/filter audit còn thiếu xác nhận; nhãn grounding cần được người nộp kiểm tra lại với trace và PDF. Kết quả không đại diện cho corpus khác.
- **Cải tiến:** bổ sung `chapter` đáng tin từ cấu trúc PDF/manifest, kiểm tra filter trước retrieval, hoàn thành coherence audit trên chunk gốc và xác minh metadata/filter, thử chunking theo câu/heading, tăng kích thước test và lưu đầy đủ phiên bản, thời gian, chunk count.
