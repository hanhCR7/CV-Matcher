# CV-JD Matcher 🚀

Hệ thống hỗ trợ nhà tuyển dụng tự động phân tích CV, trích xuất dữ liệu có cấu trúc và đánh giá mức độ tương thích giữa Hồ sơ ứng viên (CV) và Bản mô tả công việc (Job Description - JD). 

Dự án sử dụng cơ chế **Chấm điểm Hybrid (Lai)** kết hợp giữa **Local Semantic Embeddings** (so khớp ngữ nghĩa nhanh, không tốn phí) và **Google Gemini AI** (đánh giá sâu về năng lực, kinh nghiệm thực tế và red flags). Hệ thống hỗ trợ hoàn hảo cả **tiếng Việt** và **tiếng Anh**.

---

## ✨ Các Tính Năng Nổi Bật

- 📂 **Hỗ trợ đa định dạng**: Trích xuất nội dung văn bản từ các file CV/JD dạng `.pdf`, `.docx`, `.txt`, `.md` (bao gồm cả việc đọc bảng biểu trong file Word).
- 🧠 **Trích xuất dữ liệu có cấu trúc (Structured Extraction)**: Sử dụng Gemini AI định dạng cấu trúc JSON chuẩn cho thông tin CV (Họ tên, Liên hệ, Kỹ năng, Học vấn, Kinh nghiệm làm việc chi tiết) và JD (Yêu cầu kỹ năng, Học vấn, Kinh nghiệm, Trách nhiệm).
- 🎯 **Chấm điểm kết hợp Hybrid Matcher**:
  - **Embedding Score (40% trọng số)**: Sử dụng mô hình Vector Embedding đa ngôn ngữ chạy cục bộ (local) để tính độ tương đồng ngữ nghĩa của kỹ năng và profile tổng thể (ví dụ: nhận biết được `"ReactJS"` tương tự `"React"` hoặc `"Vue.js"` tương tự `"Vue"`).
  - **LLM Score (60% trọng số)**: Sử dụng Gemini AI để phân tích sâu kinh nghiệm, mức độ liên quan của dự án, độ phù hợp về cấp bậc (Seniority) và phát hiện các điểm nghi vấn (career gap, nhảy việc quá nhanh).
  - **Công thức tính điểm**: $\text{Final Score} = (0.4 \times \text{Embedding Score}) + (0.6 \times \text{LLM Score})$.
- 🌗 **Giao diện Web Premium**: Giao diện Single Page Application (SPA) tuyệt đẹp với chế độ Light/Dark Mode, hỗ trợ tìm kiếm, lọc và sắp xếp ứng viên theo mức độ phù hợp.
- ⚡ **API RESTful mạnh mẽ**: Được xây dựng trên FastAPI, tự động sinh tài liệu tích hợp Swagger UI.
- 🛡️ **Hoạt động Ngoại tuyến Linh hoạt (Offline Fallback)**: Tự động phát hiện và chuyển sang chế độ đối chiếu từ khóa chính xác khi máy chủ không có kết nối internet hoặc không đủ RAM để tải mô hình Embedding local.

---

## 🛠️ Công Nghệ Sử Dụng

### Backend
- **Python 3.12 / 3.13**
- **FastAPI**: Khung ứng dụng web API hiệu năng cao, hỗ trợ Asynchronous (async/await).
- **Google GenAI SDK**: Kết nối trực tiếp với các mô hình Gemini thế hệ mới (mặc định sử dụng `gemini-2.5-flash`, có thể đổi qua biến `GEMINI_MODEL`).
- **Sentence-Transformers**: Tạo vector biểu diễn văn bản cục bộ bằng mô hình `paraphrase-multilingual-MiniLM-L12-v2`.
- **pdfplumber & python-docx**: Thư viện xử lý và bóc tách nội dung tệp tin văn bản.
- **SQLite**: Hệ quản trị cơ sở dữ liệu lưu trữ local nhanh gọn, không cần cấu hình cài đặt phức tạp.

### Frontend
- **Vanilla HTML5 & CSS3**: Giao diện tùy biến chuyên sâu sử dụng CSS Variables, hiệu ứng Glassmorphism và tối ưu hóa hiển thị Responsive.
- **Vanilla JavaScript**: Fetch API bất đồng bộ để tương tác trực tiếp với Backend, quản lý trạng thái hiển thị thời gian thực (no-build step).

---

## 📁 Cấu Trúc Thư Mục

```text
cv-jd-matcher/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI server, định nghĩa API và tích hợp giao diện tĩnh
│   │   ├── models.py        # Định nghĩa các Schema dữ liệu Pydantic (Job, Candidate, MatchResult)
│   │   ├── parser.py        # Thư viện trích xuất text từ tệp tin PDF/DOCX/TXT
│   │   ├── extractor.py     # Gọi API Gemini để phân tích văn bản sang JSON có cấu trúc
│   │   ├── embeddings.py    # Xử lý vector embedding cục bộ để so khớp ngữ nghĩa kỹ năng
│   │   ├── matcher.py       # Thuật toán lai (Hybrid) tính điểm tương thích
│   │   └── storage.py       # Quản lý lưu trữ SQLite cục bộ (jobs, candidates)
│   ├── tests/               # Bộ test pytest (giả lập Gemini và model embedding, không cần mạng)
│   ├── requirements.txt     # Danh sách thư viện Python cần cài đặt
│   ├── requirements-dev.txt # Thư viện chạy test (kèm requirements.txt + pytest)
│   ├── .env.example         # File mẫu cấu hình biến môi trường
│   └── .env                 # File cấu hình thật và API Key (tạo từ .env.example, không commit)
└── frontend/
    └── index.html           # File giao diện Single Page Application chính
```

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Ứng Dụng

### 1. Chuẩn bị Môi trường Backend
Di chuyển vào thư mục `backend` và khởi tạo môi trường ảo Python:

```bash
cd backend

# Khuyến nghị sử dụng Python 3.12 hoặc 3.13 để tránh các lỗi biên dịch thư viện trên Python 3.14+
python3 -m venv venv
source venv/bin/activate  # Trên Windows: venv\Scripts\activate

# Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```

### 2. Cấu hình Biến Môi trường (`.env`)
Tạo tệp `.env` từ tệp mẫu `.env.example` trong thư mục `backend`:

```bash
cp .env.example .env
```

Nhập các khóa cấu hình sau vào `.env`:
```ini
# Bắt buộc: API Key của Google Gemini (Lấy miễn phí tại https://aistudio.google.com)
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE

# Tùy chọn: Chọn mô hình hoạt động (Mặc định: gemini-2.5-flash)
GEMINI_MODEL=gemini-2.5-flash

# Tùy chọn: Tên file database lưu trữ dữ liệu (Mặc định: cv_matcher.db)
CV_MATCHER_DB=cv_matcher.db
```

### 3. Khởi chạy Server Backend
Khởi chạy ứng dụng thông qua Uvicorn:

```bash
uvicorn app.main:app --reload --port 8000
```

> **Lưu ý trong lần chạy đầu tiên**: Hệ thống sẽ tự động tải mô hình Vector Embedding đa ngôn ngữ `paraphrase-multilingual-MiniLM-L12-v2` (~470MB) từ HuggingFace về máy chủ. Quá trình này cần kết nối Internet và mất từ 1-3 phút tùy thuộc vào tốc độ mạng. Ở các lần chạy tiếp theo, mô hình sẽ được đọc trực tiếp từ bộ nhớ đệm (cache) cục bộ.

### 4. Truy cập Giao diện & API Docs
- Giao diện người dùng Web: **[http://localhost:8000](http://localhost:8000)** (phục vụ trực tiếp từ FastAPI, không lo lỗi CORS).
- Tài liệu API tương tác (Swagger UI): **[http://localhost:8000/docs](http://localhost:8000/docs)**.

---

## 🧪 Chạy Test

Bộ test dùng dữ liệu giả lập cho Gemini và model embedding, nên không cần API key hay kết nối mạng:

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Nếu phát hiện một lỗi mà chưa kịp sửa, bạn có thể viết trước test tái hiện lỗi đó và đánh dấu `@pytest.mark.xfail(strict=True)`; khi sửa xong, pytest sẽ nhắc bỏ dấu `xfail`.

---

## 🛰️ Chi Tiết API Endpoints

| Method | Endpoint | Mô tả |
| :--- | :--- | :--- |
| **POST** | `/api/jobs` | Tạo mới Job từ nội dung JD văn bản dán trực tiếp (`{"raw_text": "..."}`) |
| **POST** | `/api/jobs/upload` | Tạo mới Job bằng cách upload file JD (.pdf, .docx, .txt) |
| **GET** | `/api/jobs` | Lấy danh sách toàn bộ các vị trí tuyển dụng (Jobs) |
| **GET** | `/api/jobs/{job_id}` | Lấy thông tin chi tiết của một vị trí tuyển dụng |
| **DELETE** | `/api/jobs/{job_id}` | Xóa vị trí tuyển dụng và toàn bộ hồ sơ ứng viên đi kèm |
| **POST** | `/api/jobs/{job_id}/candidates` | Upload danh sách CV ứng viên (chấp nhận nhiều tệp tin cùng lúc). Trả về `{"candidates": [...], "errors": [{"filename", "detail"}]}`: file nào lỗi sẽ nằm trong `errors`, các file còn lại vẫn được xử lý. Trả 422 nếu không file nào xử lý được |
| **GET** | `/api/jobs/{job_id}/candidates` | Xem danh sách ứng viên của vị trí đó (đã sắp xếp theo điểm phù hợp giảm dần) |
| **DELETE** | `/api/candidates/{candidate_id}`| Xóa hồ sơ của một ứng viên cụ thể (404 nếu không tồn tại) |
| **GET** | `/api/health` | Kiểm tra trạng thái hoạt động của hệ thống và mô hình Embedding local |

---

## 📝 Lưu Ý Triển Khai Thực Tế

1. **Chi phí API Gemini**: Mỗi CV gửi lên sẽ thực hiện 2 lượt gọi mô hình (1 lượt để trích xuất thông tin có cấu trúc, 1 lượt để đối chiếu & đánh giá). Chi phí sử dụng của dòng mô hình Gemini Flash rất thấp, hoàn toàn phù hợp để xử lý hàng ngàn hồ sơ mỗi tháng với mức phí tối thiểu.
2. **Quét dữ liệu PDF dạng hình ảnh (Scanned PDF)**: Trình bóc tách văn bản mặc định (`parser.py`) chỉ trích xuất được text kỹ thuật số thực sự. Đối với các CV được xuất bản dạng ảnh quét không có lớp text ẩn, bạn nên tích hợp thêm công cụ OCR (ví dụ như Tesseract OCR hoặc Google Cloud Vision) trước khi đưa vào module Extractor.
3. **Bảo mật dữ liệu**: Dữ liệu tuyển dụng và thông tin cá nhân của ứng viên hiện đang được lưu trữ cục bộ trong file SQLite (`cv_matcher.db`). Khi triển khai lên môi trường dùng chung cho doanh nghiệp, bạn nên tích hợp thêm lớp Middleware xác thực người dùng (Authentication) và chuyển đổi cơ sở dữ liệu sang PostgreSQL để tăng tính phân quyền và chịu tải.
4. **Mở rộng hàng đợi (Queue)**: Đối với các hệ thống cần xử lý hàng trăm CV cùng một lúc, nên sử dụng các kiến trúc hàng đợi bất đồng bộ (như Celery với Redis) để tránh tình trạng timeout yêu cầu HTTP từ phía client.

---

## 📄 Giấy phép

Dự án được phân phối dưới giấy phép MIT License. Bạn hoàn toàn có thể sử dụng và sửa đổi cho mục đích nội bộ hoặc thương mại.
