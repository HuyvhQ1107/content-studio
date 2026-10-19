"""Backend FastAPI: đăng ký/đăng nhập, lưu lịch sử vào PostgreSQL, chạy CrewAI nền.

Chạy từ thư mục gốc:  python run.py   rồi mở http://127.0.0.1:8000
"""

import hashlib
import hmac
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.crew_service import missing_keys, run_crew
from database.db import AuthSession, Base, Conversation, Message, SessionLocal, User, engine

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
COOKIE = "cs_session"
SESSION_DAYS = 30
executor = ThreadPoolExecutor(max_workers=2)  # tối đa 2 crew chạy cùng lúc


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)  # tự tạo bảng nếu chưa có
    with SessionLocal() as db:  # tác vụ đang dở khi server tắt không thể tiếp tục
        db.execute(
            update(Message).where(Message.status == "running").values(
                status="error",
                error="Máy chủ đã khởi động lại nên tác vụ bị gián đoạn. Hãy gửi lại chủ đề.",
            )
        )
        db.commit()
    yield


app = FastAPI(title="Content Studio", lifespan=lifespan)


@app.middleware("http")
async def no_cache_frontend(request: Request, call_next):
    # Trình duyệt luôn hỏi lại server (nhẹ nhờ ETag), nên sửa giao diện không bị kẹt bản cũ
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/frontend"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def get_db():
    with SessionLocal() as db:
        yield db


# ---------------------------------------------------------------- mật khẩu
def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{h.hex()}"


def check_pw(pw: str, stored: str) -> bool:
    salt_hex, h_hex = stored.split(":")
    h = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(h.hex(), h_hex)


# ---------------------------------------------------------------- phiên đăng nhập
def _start_session(db: Session, response: Response, user: User) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db.add(AuthSession(token=token, user_id=user.id, expires_at=expires))
    db.commit()
    response.set_cookie(
        COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "").lower() in ("1", "true", "yes"),  # bật khi chạy sau HTTPS
    )


def _user_from_cookie(request: Request, db: Session) -> User | None:
    token = request.cookies.get(COOKIE)
    s = db.get(AuthSession, token) if token else None
    if not s:
        return None
    exp = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)
    return s.user if exp > datetime.now(timezone.utc) else None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_cookie(request, db)
    if not user:
        raise HTTPException(401, "Chưa đăng nhập")
    return user


class AuthRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,30}$")
    password: str = Field(min_length=8, max_length=128)
    invite_code: str = Field(default="", max_length=100)


@app.get("/api/auth/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = _user_from_cookie(request, db)
    return {
        "user": user.username if user else None,
        "invite_required": bool(os.getenv("INVITE_CODE")),
    }


@app.post("/api/auth/register")
def register(req: AuthRequest, db: Session = Depends(get_db)):
    code = os.getenv("INVITE_CODE", "")
    if code and not hmac.compare_digest(req.invite_code.encode(), code.encode()):
        raise HTTPException(403, "Mã mời không đúng")
    user = User(username=req.username.lower(), password_hash=hash_pw(req.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Tên đăng nhập đã tồn tại")
    # Không tạo phiên đăng nhập ở đây: người dùng tự đăng nhập sau khi đăng ký
    return {"username": user.username}


@app.post("/api/auth/login")
def login(req: AuthRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == req.username.lower()))
    if not user or not check_pw(req.password, user.password_hash):
        raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu")
    _start_session(db, response, user)
    return {"username": user.username}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    s = db.get(AuthSession, token) if token else None
    if s:
        db.delete(s)
        db.commit()
    response.delete_cookie(COOKIE)
    return {"ok": True}


# ---------------------------------------------------------------- hội thoại
def msg_out(m: Message) -> dict:
    return {
        "id": m.id, "role": m.role, "text": m.text, "status": m.status,
        "done": m.done, "total": m.total, "result": m.result, "error": m.error,
    }


def _own_conversation(db: Session, user: User, cid: int) -> Conversation:
    conv = db.get(Conversation, cid)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy cuộc trò chuyện")
    return conv


@app.get("/api/conversations")
def list_conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return {"conversations": [{"id": c.id, "title": c.title} for c in rows]}


@app.get("/api/conversations/{cid}")
def get_conversation(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = _own_conversation(db, user, cid)
    return {"messages": [msg_out(m) for m in conv.messages]}


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_conversation(db, user, cid))
    db.commit()
    return {"ok": True}


@app.get("/api/messages/{mid}")
def get_message(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.scalar(
        select(Message).join(Conversation)
        .where(Message.id == mid, Conversation.user_id == user.id)
    )
    if not m:
        raise HTTPException(404, "Không tìm thấy tin nhắn")
    return msg_out(m)


# ---------------------------------------------------------------- gửi chủ đề
class ChatRequest(BaseModel):
    conversation_id: int | None = None
    topic: str = Field(min_length=3, max_length=300)
    language: str = Field(default="Vietnamese", max_length=30)
    with_social: bool = True


def _worker(msg_id: int, req: ChatRequest) -> None:
    def save(**values) -> None:
        with SessionLocal() as db:
            db.execute(update(Message).where(Message.id == msg_id).values(**values))
            db.commit()

    try:
        result = run_crew(
            req.topic, req.language, req.with_social,
            on_task_done=lambda n: save(done=n),
        )
        save(status="done", result=result)
    except Exception as exc:  # báo lỗi cho giao diện thay vì làm sập server
        save(status="error", error=f"{type(exc).__name__}: {exc}")


@app.post("/api/chat")
def chat(req: ChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    missing = missing_keys()
    if missing:
        raise HTTPException(500, f"Server thiếu biến môi trường: {', '.join(missing)} (kiểm tra file .env)")

    running = db.scalar(
        select(func.count()).select_from(Message).join(Conversation)
        .where(Conversation.user_id == user.id, Message.status == "running")
    )
    if running:
        raise HTTPException(409, "Bạn đang có một tác vụ chạy. Hãy chờ nó hoàn tất.")

    if req.conversation_id:
        conv = _own_conversation(db, user, req.conversation_id)
    else:
        conv = Conversation(user_id=user.id, title=req.topic[:40])
        db.add(conv)
        db.flush()

    user_msg = Message(conversation_id=conv.id, role="user", text=req.topic, status="done")
    bot_msg = Message(
        conversation_id=conv.id, role="assistant", status="running",
        total=3 if req.with_social else 2,
    )
    db.add_all([user_msg, bot_msg])
    conv.updated_at = func.now()
    db.commit()

    executor.submit(_worker, bot_msg.id, req)
    return {
        "conversation": {"id": conv.id, "title": conv.title},
        "messages": [msg_out(user_msg), msg_out(bot_msg)],
    }


app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")