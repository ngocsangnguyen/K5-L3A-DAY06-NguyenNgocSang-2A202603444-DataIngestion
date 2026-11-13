## Dữ liệu và pipeline
- **Chủ đề/corpus:** *Introduction to Computer Science* (OpenStax); 1 tài liệu PDF, `document_id=openstax-intro-cs`. Nguồn: https://assets.openstax.org/oscms-prodcms/media/documents/Introduction_To_Computer_Science_-_WEB.pdf. Trang vật lý 4 và phần Preface trang 11 của PDF xác nhận CC BY-NC-SA 4.0: chỉ sử dụng phi thương mại, ghi công và chia sẻ phái sinh cùng giấy phép. Giữ nguyên attribution “Access for free at openstax.org”; hình minh họa có thể có điều khoản/attribution riêng như mô tả trong PDF.
- **Số trang:** manifest hiện tại khai báo **34 trang nội dung** (trang vật lý 19–40 và 49–60; PDF có 939 trang vật lý). Pipeline kiểm tra các trang được chọn không rỗng và đối chiếu evidence quote với văn bản trích xuất.
- **Chuẩn hóa và lỗi:** `load_pdf` trích xuất PDF, chuẩn hóa Unicode NFC và khoảng trắng; mỗi chunk giữ `document_id`, nguồn, trang và metadata. Quote q08 đã được sửa để khớp văn bản trích xuất từ trang 22. Log có cảnh báo hai trang đầu rỗng; đây không phải các trang nội dung được chọn trong manifest.
- **Embedding:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, chạy local trên CPU; **384 chiều**, cùng model cho A/B/C. Môi trường: Python 3.11.9, Sentence Transformers 6.3.0, PyTorch 2.15.0, PyMuPDF 2.1.0.
- **Vector store:** PostgreSQL 16.16 + pgvector extension 0.8.7; Python `pgvector` 0.5.1 và `psycopg` 3.3.8. Bảng `ingestion_chunks`, khóa chính `(strategy,chunk_id)`, cosine distance (`<=>`), truy xuất Top 3. Lệnh chạy:

```bash
python -m starter.src.run --manifest data/manifest.json --benchmark data/benchmark/questions.json --output results --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

- **Chi phí:** embedding chạy local nên không phát sinh chi phí API trong pipeline; không tính điện, phần cứng, Internet và thời gian nhân công.
- **Metadata:** `document_id`, `source`, `page` lưu ở các cột riêng; `category=computer_science`, `language=en` lấy từ manifest. `chapter` được gán theo từng trang từ `data/page_inventory.csv` và khai báo lại trong `data/manifest.json`; các trường metadata được lưu trong JSONB. Q17/q19 dùng `chapter_2`; strategy C lọc đúng theo trường này.

## Cấu hình và benchmark
- **A:** `fixed_size(size=500, overlap=50)`, không filter.
- **B:** `by_paragraph(max_size=500)`, không filter; đoạn dài hơn 500 vẫn bị cắt theo ký tự.
- **C:** chunking giống hệt B; thêm `metadata @> question.filter` nếu câu hỏi cung cấp filter. Đây là so sánh chỉ thay một yếu tố giữa B–C.
- **Benchmark:** 20 câu, 15 dev + 5 test (q01–q15 và q16–q20); có câu hỏi filter và gold evidence. `run.py` xác minh quote có trong trang nguồn sau chuẩn hóa trước khi đánh giá. Trên mỗi chiến lược, dùng cùng model, corpus, benchmark và truy xuất Top 3. File hiện tại xác nhận số lượng/split và kiểm chứng quote; lịch sử không chứng minh được benchmark đã được đóng băng trước lần chạy đầu.
- **Tiêu chí lựa chọn:** ưu tiên Evidence Hit@3 trên **dev**, sau đó Hit@1 và chất lượng audit. Đây là tiêu chí diễn giải; không có bằng chứng đã ghi lại trước khi xem test, nên không khẳng định đã pre-register.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Ingest (s) | Chi phí API |
|---|---|---|---|---|---|---|
| A | dev | 7/15 (46.67%) | 11/15 (73.33%) | 251 | 37.188 | 0 USD |
| A | test | 3/5 (60.00%) | 3/5 (60.00%) | 251 | 37.188 | 0 USD |
| B | dev | 6/15 (40.00%) | 8/15 (53.33%) | 317 | 29.171 | 0 USD |
| B | test | 1/5 (20.00%) | 3/5 (60.00%) | 317 | 29.171 | 0 USD |
| C | dev | 6/15 (40.00%) | 8/15 (53.33%) | 317 | 28.138 | 0 USD |
| C | test | 2/5 (40.00%) | 3/5 (60.00%) | 317 | 28.138 | 0 USD |

*Embedding chạy local nên không phát sinh chi phí API; không tính điện, phần cứng, Internet hoặc thời gian nhân công. Số chunk và thời gian ingestion lấy từ `results/run_metadata.json`.*

### Manual Audit

| Strategy | Grounding 0/1/2; mean /2 (5 câu) | Coherence 0/1/2; mean /2 (10 vị trí) | Metadata đúng (15 hit top-3) | Filter q17/q19 tuân thủ |
|---|---|---|---:|---:|
| A | 0/2/3; 1.6 | 0/10/0; 1.0 | 15/15 | 2/2 (không áp dụng filter; kết quả tình cờ cùng chapter) |
| B | 0/2/3; 1.6 | 0/5/5; 1.5 | 15/15 | 1/2 (control không filter; q17 có hit chapter_1) |
| C | 0/2/3; 1.6 | 0/5/5; 1.5 | 15/15 | 2/2 (đã áp dụng filter chapter_2) |

Grounding scores dùng rubric 0/1/2 của GUIDE trên q16–q20: q16 và q20 có nội dung liên quan nhưng không đủ gold evidence (1); q17–q19 có bằng chứng đủ và truy nguồn được (2). Coherence dùng cùng 10 vị trí đã chọn trước khi chấm: đoạn văn nội dung đầu tiên dài ít nhất 200 ký tự trên mỗi trang vật lý 19–28; với mỗi strategy chấm chunk chứa 80 ký tự đầu của đoạn đó. Điểm 0/1/2 lần lượt là 0 = ý bị cắt/không hiểu, 1 = hiểu một phần, 2 = tự hiểu được và giữ trọn ý.

**Giới hạn audit:** các coherence scores là đánh giá hỗ trợ bởi AI sau khi đọc từng chunk mẫu, không phải xác nhận độc lập của học viên; học viên cần xác nhận nhãn trước khi nộp nếu rubric yêu cầu audit thủ công. Grounding labels cũng cần học viên kiểm tra lại với PDF/trace. Kiểm tra metadata đối chiếu `document_id`, nguồn, trang, `category`, `language` và `chapter` của 15 hit top-3 mỗi strategy với manifest/page inventory. Filter compliance đo ở cấp câu hỏi (cả top-3 phải khớp filter): A 2/2 và B 1/2 là control không filter; C 2/2 là strategy có filter.

Đã xuất toàn bộ **885 chunk** vào `results/audit_chunks.csv` (A: 251, B: 317, C: 317), kèm JSON metadata để kiểm tra. Đây là tệp dữ liệu; không đồng nghĩa mọi chunk đã được audit thủ công. Chi tiết 45 nhãn (15 grounding + 30 coherence) và chunk ID mẫu nằm trong `results/manual_audit_reviewed.csv`.


## Phân tích và kết luận

- **A–B:** A hơn B trên dev: Hit@1 46,67% so với 40%; Hit@3 73,33% so với 53,33%. Khác biệt chính là fixed-size có overlap so với paragraph-based. Kết quả không đủ để chứng minh mọi corpus đều phù hợp fixed-size.
- **B–C:** B và C có cùng chunking, chỉ khác việc áp dụng filter. Sau khi gắn `chapter` từ page inventory, C đạt cùng Hit@3 với B (dev 8/15, test 3/5), Hit@1 test tăng từ 1/5 lên 2/5, và top-3 tuân thủ filter ở 2/2 câu q17/q19. Đây là kết quả của corpus/benchmark hiện tại; không chứng minh lọc metadata luôn cải thiện recall.
- **Ví dụ sai 1 — q16 (test):** hỏi sự khác biệt giữa machine learning và quy tắc thủ công. Strategy A trả về trang 35, 31, 60 nhưng không có `evidence_hit` trong Top 3; B/C cũng không hit. Có thông tin liên quan đến ML nhưng chưa trúng gold evidence.
- **Ví dụ sai 2 — q20 (test):** hỏi biểu diễn trực quan các bước thuật toán. Strategy A trả về trang 53, 20 và một chunk khác nhưng không chứa đủ gold evidence trong Top 3; B/C cũng không hit. Truy xuất theo ngữ nghĩa gần chưa đủ đảm bảo chứa bằng chứng cụ thể.
- **Chiến lược được chọn:** **A**, dựa trên Hit@3 dev cao nhất (11/15) và Hit@1 test 3/5; phù hợp làm baseline cho corpus/benchmark hiện tại. Đánh đổi là fixed-size có thể cắt giữa câu, cần kiểm chứng coherence.
- **Hạn chế:** chỉ một PDF, 20 câu và 5 câu test; kết quả phụ thuộc gold evidence và cách chia chunk. Coherence labels được AI hỗ trợ và cần học viên xác nhận; không có bằng chứng file hiện tại rằng benchmark đã đóng băng trước lần chạy đầu. Kết quả không đại diện cho corpus khác.
- **Cải tiến:** học viên xác nhận coherence/grounding labels trước khi nộp; tăng kích thước test; thử chunking theo câu/heading; tiếp tục lưu phiên bản, thời gian, chunk count và audit trace.
