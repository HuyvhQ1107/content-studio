# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Công cụ biên dịch, phòng khi có thư viện Python cần build từ mã nguồn
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Chạy app bằng user thường thay vì root
RUN useradd -m -u 1000 app && mkdir /app && chown app:app /app
WORKDIR /app

# Cài thư viện trước để Docker cache lại khi chỉ sửa code
COPY requirements.txt .
# Cache pip giữa các lần build: nếu mạng đứt giữa chừng, lần build lại không phải tải lại từ đầu
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=100 --retries 10 -r requirements.txt

COPY backend ./backend
COPY database ./database
COPY frontend ./frontend
COPY run.py .

USER app
EXPOSE 8000
CMD ["python", "run.py"]