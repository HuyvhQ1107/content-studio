"""Điểm khởi chạy. Chạy file này trong PyCharm hoặc: python run.py"""

import os

import uvicorn

from backend.main import app

if __name__ == "__main__":
    # Trong Docker, HOST được đặt là 0.0.0.0 (xem docker-compose.yml)
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )
