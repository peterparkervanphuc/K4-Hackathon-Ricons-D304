# VLearn Tutor Backend

Chạy từ thư mục repository chính:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
py -m uvicorn api:app --reload --port 8000
```

`api.py` chứa biến FastAPI `app`; Swagger API có tại `http://localhost:8000/docs`.

OpenAI là provider chính cho generation, vision và embedding. Cấu hình `backend/.env` từ `.env.example`; file `.env` đã được Git ignore. Nếu OpenAI thiếu key hoặc lỗi runtime, generation/vision thử Groq khi có `GROQ_API_KEY`; embedding không bị thay bằng dữ liệu giả và sẽ báo lỗi cấu hình rõ ràng.
