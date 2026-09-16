from __future__ import annotations

import os
import secrets
import shutil
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, and_, create_engine, event, func, inspect, or_, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env", override=False)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bondbook.db")
if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.startswith("sqlite:////") and DATABASE_URL != "sqlite:///:memory:":
    database_file = DATABASE_URL.replace("sqlite:///", "", 1)
    DATABASE_URL = f"sqlite:///{(BASE_DIR / database_file).resolve()}"
# Render supplies a standard Postgres URL. SQLAlchemy needs the explicit
# psycopg v3 dialect installed by requirements.txt.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me-before-deployment")
ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(exist_ok=True)

engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)

if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_color: Mapped[str] = mapped_column(String(20), default="#8267d6")
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    friend_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True)
    theme: Mapped[str] = mapped_column(String(10), default="light")
    background: Mapped[str] = mapped_column(String(24), default="cream")
    font: Mapped[str] = mapped_column(String(24), default="classic")
    sticker: Mapped[str] = mapped_column(String(24), default="heart")
    cover_style: Mapped[str] = mapped_column(String(24), default="lavender")
    friendship_nickname: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    friend: Mapped[Optional["User"]] = relationship("User", remote_side=[id], uselist=False)
    memories: Mapped[list["Memory"]] = relationship(back_populates="owner", cascade="all, delete-orphan", foreign_keys="Memory.owner_id")

class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    memory_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    category: Mapped[str] = mapped_column(String(32), default="Happy", index=True)
    tags: Mapped[str] = mapped_column(String(500), default="")
    mood: Mapped[str] = mapped_column(String(40), default="Warm")
    location: Mapped[str] = mapped_column(String(140), default="")
    visibility: Mapped[str] = mapped_column(String(12), default="Private", index=True)
    # The specific friend who was intentionally selected when the entry was shared.
    # This prevents a future connection from seeing entries meant for a former friend.
    shared_with_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_reflection: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    owner: Mapped[User] = relationship(back_populates="memories", foreign_keys=[owner_id])
    media: Mapped[list["Media"]] = relationship(back_populates="memory", cascade="all, delete-orphan")
    responses: Mapped[list["ReflectionResponse"]] = relationship(back_populates="reflection", cascade="all, delete-orphan")

class Media(Base):
    __tablename__ = "media"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    memory: Mapped[Memory] = relationship(back_populates="media")

class ReflectionResponse(Base):
    __tablename__ = "reflection_responses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reflection_id: Mapped[int] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    reflection: Mapped[Memory] = relationship(back_populates="responses")
    author: Mapped[User] = relationship(foreign_keys=[author_id])

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    memory_id: Mapped[Optional[int]] = mapped_column(ForeignKey("memories.id", ondelete="SET NULL"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

class OpenWhenLetter(Base):
    __tablename__ = "open_when_letters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    recipient_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    occasion: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(12), default="Private", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class DuoGame(Base):
    __tablename__ = "duo_games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_one_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    player_two_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    board: Mapped[str] = mapped_column(String(9), default="---------", nullable=False)
    turn_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    winner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)

Base.metadata.create_all(bind=engine)

def ensure_schema_compatibility():
    """Add non-destructive columns required by newer BondBook versions.

    SQLite's create_all does not alter an existing table. Existing shared rows are
    deliberately left without a recipient, so the owner must explicitly re-share
    them rather than exposing them to a later connection by accident.
    """
    with engine.begin() as connection:
        memory_columns = {column["name"] for column in inspect(engine).get_columns("memories")}
        if "shared_with_id" not in memory_columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN shared_with_id INTEGER"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memories_shared_with_id ON memories (shared_with_id)"))
        user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
        additions = {
            "background": "VARCHAR(24) NOT NULL DEFAULT 'cream'",
            "font": "VARCHAR(24) NOT NULL DEFAULT 'classic'",
            "sticker": "VARCHAR(24) NOT NULL DEFAULT 'heart'",
            "cover_style": "VARCHAR(24) NOT NULL DEFAULT 'lavender'",
            "friendship_nickname": "VARCHAR(80) NOT NULL DEFAULT ''",
        }
        for column, definition in additions.items():
            if column not in user_columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {column} {definition}"))

ensure_schema_compatibility()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    avatar_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    theme: Optional[Literal["light", "dark", "lavender", "rose", "midnight"]] = None
    background: Optional[Literal["cream", "lavender", "blush", "sky", "midnight"]] = None
    font: Optional[Literal["classic", "modern", "rounded"]] = None
    sticker: Optional[Literal["heart", "sparkles", "flower", "moon"]] = None
    cover_style: Optional[Literal["lavender", "blush", "sunset", "night"]] = None
    friendship_nickname: Optional[str] = Field(default=None, max_length=80)

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

class MemoryInput(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(default="", max_length=10000)
    memory_date: date
    category: Literal["Happy", "Funny", "Special Day", "Difficult Moment", "Reflection", "Milestone"] = "Happy"
    tags: str = Field(default="", max_length=500)
    mood: str = Field(default="Warm", max_length=40)
    location: str = Field(default="", max_length=140)
    visibility: Literal["Private", "Draft", "Shared"] = "Private"
    is_reflection: bool = False
    confirmed_share: bool = False

class VisibilityInput(BaseModel):
    visibility: Literal["Private", "Draft", "Shared"]
    confirmed: bool = False

class ConnectionInput(BaseModel):
    invite_code: str = Field(min_length=6, max_length=16)

class ResponseInput(BaseModel):
    message: str = Field(min_length=1, max_length=3000)

class ChatMessageInput(BaseModel):
    message: str = Field(min_length=1, max_length=3000)

class LetterInput(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    occasion: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=10000)
    visibility: Literal["Private", "Draft", "Shared"] = "Private"
    confirmed_share: bool = False

class GameMoveInput(BaseModel):
    position: int = Field(ge=0, le=8)

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def friendly_error(detail: str, code=status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=code, detail=detail)

def new_invite_code(db: Session) -> str:
    while True:
        code = secrets.token_urlsafe(6).upper().replace("-", "").replace("_", "")[:8]
        if not db.scalar(select(User).where(User.invite_code == code)):
            return code

def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)

def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(db_session)) -> User:
    credentials_error = HTTPException(status_code=401, detail="Your session has expired. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError, TypeError):
        raise credentials_error
    user = db.get(User, user_id)
    if not user:
        raise credentials_error
    return user

def user_data(user: User, db: Session) -> dict:
    friend = db.get(User, user.friend_id) if user.friend_id else None
    return {"id": user.id, "name": user.name, "email": user.email, "avatar_color": user.avatar_color, "invite_code": user.invite_code, "theme": user.theme, "background": user.background, "font": user.font, "sticker": user.sticker, "cover_style": user.cover_style, "friendship_nickname": user.friendship_nickname, "friend": {"id": friend.id, "name": friend.name, "email": friend.email, "avatar_color": friend.avatar_color} if friend else None, "created_at": user.created_at}

def visible_memories_for(user: User):
    if not user.friend_id:
        return Memory.owner_id == user.id
    return or_(
        Memory.owner_id == user.id,
        and_(
            Memory.owner_id == user.friend_id,
            Memory.visibility == "Shared",
            Memory.shared_with_id == user.id,
        ),
    )

def can_view(memory: Memory, user: User) -> bool:
    return memory.owner_id == user.id or (
        memory.visibility == "Shared"
        and memory.shared_with_id == user.id
        and user.friend_id == memory.owner_id
    )

def memory_data(memory: Memory, db: Session, include_responses: bool = True) -> dict:
    owner = db.get(User, memory.owner_id)
    data = {"id": memory.id, "owner_id": memory.owner_id, "owner_name": owner.name if owner else "Unknown", "owner_color": owner.avatar_color if owner else "#8267d6", "title": memory.title, "description": memory.description, "memory_date": memory.memory_date, "category": memory.category, "tags": memory.tags, "mood": memory.mood, "location": memory.location, "visibility": memory.visibility, "shared_with_id": memory.shared_with_id, "is_reflection": memory.is_reflection, "created_at": memory.created_at, "updated_at": memory.updated_at, "media": [{"id": item.id, "name": item.original_name, "content_type": item.content_type, "kind": item.kind, "size": item.size, "url": f"/api/media/{item.id}"} for item in memory.media]}
    if include_responses:
        data["responses"] = [{"id": r.id, "message": r.message, "author_id": r.author_id, "author_name": r.author.name, "author_color": r.author.avatar_color, "created_at": r.created_at} for r in memory.responses]
    return data

def notify(db: Session, user_id: int, type_: str, message: str, memory_id: Optional[int] = None):
    db.add(Notification(user_id=user_id, type=type_, message=message, memory_id=memory_id))

def connected_friend(user: User, db: Session) -> User:
    friend = db.get(User, user.friend_id) if user.friend_id else None
    if not friend or friend.friend_id != user.id:
        friendly_error("Connect with your friend before opening the chat.", 403)
    return friend

def chat_data(message: ChatMessage, user: User) -> dict:
    return {"id": message.id, "message": message.message, "sender_id": message.sender_id, "is_mine": message.sender_id == user.id, "created_at": message.created_at}

app = FastAPI(title="BondBook API", version="1.0.0")
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def root():
    return {"status": "ok", "service": "BondBook API", "health": "/api/health", "docs": "/docs"}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "BondBook API"}

@app.post("/api/auth/register", status_code=201)
def register(payload: UserCreate, db: Session = Depends(db_session)):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        friendly_error("An account with this email already exists.", 409)
    user = User(name=payload.name.strip(), email=email, password_hash=pwd_context.hash(payload.password), invite_code=new_invite_code(db))
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": user_data(user, db)}

@app.post("/api/auth/login")
def login(payload: LoginInput, db: Session = Depends(db_session)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not pwd_context.verify(payload.password, user.password_hash):
        friendly_error("Incorrect email or password.", 401)
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": user_data(user, db)}

@app.get("/api/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(db_session)):
    return user_data(user, db)

@app.patch("/api/users/me")
def update_profile(payload: UserUpdate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value.strip() if isinstance(value, str) and field in {"name", "friendship_nickname"} else value)
    db.commit(); db.refresh(user)
    return user_data(user, db)

@app.post("/api/users/me/password", status_code=204)
def change_password(payload: PasswordUpdate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    if not pwd_context.verify(payload.current_password, user.password_hash):
        friendly_error("Your current password is incorrect.", 400)
    user.password_hash = pwd_context.hash(payload.new_password)
    db.commit()

@app.delete("/api/users/me", status_code=204)
def delete_account(user: User = Depends(current_user), db: Session = Depends(db_session)):
    if user.friend_id:
        friend = db.get(User, user.friend_id)
        if friend: friend.friend_id = None; notify(db, friend.id, "connection", f"{user.name} disconnected from your BondBook.")
    for media in db.scalars(select(Media).join(Memory).where(Memory.owner_id == user.id)).all():
        path = UPLOAD_DIR / media.stored_name
        if path.exists(): path.unlink()
    db.delete(user); db.commit()

@app.post("/api/friends/connect")
def connect_friend(payload: ConnectionInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    if user.friend_id:
        friendly_error("Disconnect your current friend before connecting someone new.")
    code = payload.invite_code.upper().replace(" ", "")
    friend = db.scalar(select(User).where(User.invite_code == code))
    if not friend: friendly_error("That invitation code was not found.", 404)
    if friend.id == user.id: friendly_error("You cannot use your own invitation code.")
    if friend.friend_id: friendly_error("That friend is already connected to someone else.")
    user.friend_id = friend.id; friend.friend_id = user.id
    notify(db, friend.id, "friend_request", f"{user.name} connected with you on BondBook.")
    notify(db, user.id, "friend_request", f"You and {friend.name} are now connected.")
    db.commit(); db.refresh(user)
    return user_data(user, db)

@app.post("/api/friends/invite-code")
def regenerate_code(user: User = Depends(current_user), db: Session = Depends(db_session)):
    user.invite_code = new_invite_code(db); db.commit()
    return {"invite_code": user.invite_code}

@app.delete("/api/friends/disconnect", status_code=204)
def disconnect_friend(user: User = Depends(current_user), db: Session = Depends(db_session)):
    if not user.friend_id: friendly_error("You are not currently connected to a friend.")
    friend = db.get(User, user.friend_id)
    if friend:
        friend.friend_id = None; notify(db, friend.id, "connection", f"{user.name} disconnected from your BondBook.")
    user.friend_id = None; db.commit()

@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(db_session)):
    visible = visible_memories_for(user)
    total = db.scalar(select(func.count()).select_from(Memory).where(Memory.owner_id == user.id, Memory.is_reflection == False)) or 0
    shared = db.scalar(select(func.count()).select_from(Memory).where(Memory.owner_id == user.id, Memory.visibility == "Shared")) or 0
    reflections = db.scalar(select(func.count()).select_from(Memory).where(visible, Memory.is_reflection == True)) or 0
    recent = db.scalars(select(Memory).where(visible).order_by(Memory.created_at.desc()).limit(6)).all()
    return {"stats": {"memories": total, "shared": shared, "reflections": reflections}, "recent": [memory_data(m, db) for m in recent]}

@app.get("/api/memories")
def list_memories(q: str = "", category: str = "", visibility: str = "", tag: str = "", media_type: str = "", date_from: Optional[date] = None, date_to: Optional[date] = None, mine_only: bool = False, reflections_only: bool = False, user: User = Depends(current_user), db: Session = Depends(db_session)):
    conditions = [Memory.is_reflection == reflections_only]
    if mine_only or not user.friend_id:
        conditions.append(Memory.owner_id == user.id)
    else:
        conditions.append(visible_memories_for(user))
    if q: conditions.append(or_(Memory.title.ilike(f"%{q.strip()}%"), Memory.description.ilike(f"%{q.strip()}%")))
    if category: conditions.append(Memory.category == category)
    if visibility: conditions.append(Memory.visibility == visibility)
    if tag: conditions.append(Memory.tags.ilike(f"%{tag.strip()}%"))
    if date_from: conditions.append(Memory.memory_date >= date_from)
    if date_to: conditions.append(Memory.memory_date <= date_to)
    statement = select(Memory).where(*conditions)
    if media_type: statement = statement.join(Media).where(Media.kind == media_type).distinct()
    memories = db.scalars(statement.order_by(Memory.memory_date.desc(), Memory.created_at.desc())).unique().all()
    return [memory_data(m, db) for m in memories]

@app.post("/api/memories", status_code=201)
def create_memory(payload: MemoryInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    values = payload.model_dump(exclude={"confirmed_share"})
    if payload.visibility == "Shared":
        if not user.friend_id: friendly_error("Connect with a friend before sharing an entry.")
        if not payload.confirmed_share: friendly_error("Please confirm before sharing this entry.")
        values["shared_with_id"] = user.friend_id
    memory = Memory(owner_id=user.id, **values)
    db.add(memory); db.flush()
    if memory.visibility == "Shared" and user.friend_id:
        notify(db, user.friend_id, "shared_memory", f"{user.name} shared “{memory.title}” with you.", memory.id)
    db.commit(); db.refresh(memory)
    return memory_data(memory, db)

@app.get("/api/memories/{memory_id}")
def get_memory(memory_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    memory = db.get(Memory, memory_id)
    if not memory or not can_view(memory, user): friendly_error("That entry is unavailable to you.", 404)
    return memory_data(memory, db)

@app.put("/api/memories/{memory_id}")
def update_memory(memory_id: int, payload: MemoryInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    memory = db.get(Memory, memory_id)
    if not memory: friendly_error("Memory not found.", 404)
    if memory.owner_id != user.id: friendly_error("Only the owner can edit this entry.", 403)
    values = payload.model_dump(exclude={"confirmed_share"})
    becoming_shared = memory.visibility != "Shared" and payload.visibility == "Shared"
    re_sharing = payload.visibility == "Shared" and user.friend_id and memory.shared_with_id != user.friend_id
    if becoming_shared or re_sharing:
        if not user.friend_id: friendly_error("Connect with a friend before sharing an entry.")
        if not payload.confirmed_share: friendly_error("Please confirm before sharing this entry.")
        values["shared_with_id"] = user.friend_id
    elif payload.visibility != "Shared":
        values["shared_with_id"] = None
    for field, value in values.items(): setattr(memory, field, value)
    if (becoming_shared or re_sharing) and user.friend_id: notify(db, user.friend_id, "shared_memory", f"{user.name} shared “{memory.title}” with you.", memory.id)
    db.commit(); db.refresh(memory)
    return memory_data(memory, db)

@app.patch("/api/memories/{memory_id}/visibility")
def update_visibility(memory_id: int, payload: VisibilityInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    memory = db.get(Memory, memory_id)
    if not memory: friendly_error("Memory not found.", 404)
    if memory.owner_id != user.id: friendly_error("Only the owner can change privacy for this entry.", 403)
    if payload.visibility == "Shared":
        needs_new_share = memory.visibility != "Shared" or (user.friend_id and memory.shared_with_id != user.friend_id)
        if needs_new_share:
            if not user.friend_id: friendly_error("Connect with a friend before sharing an entry.")
            if not payload.confirmed: friendly_error("Please confirm before sharing this entry.")
            memory.shared_with_id = user.friend_id
            notify(db, user.friend_id, "shared_memory", f"{user.name} shared “{memory.title}” with you.", memory.id)
    else:
        memory.shared_with_id = None
    memory.visibility = payload.visibility; db.commit(); db.refresh(memory)
    return memory_data(memory, db)

@app.delete("/api/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    memory = db.get(Memory, memory_id)
    if not memory: friendly_error("Memory not found.", 404)
    if memory.owner_id != user.id: friendly_error("Only the owner can delete this entry.", 403)
    for media in memory.media:
        path = UPLOAD_DIR / media.stored_name
        if path.exists(): path.unlink()
    db.delete(memory); db.commit()

ALLOWED_TYPES = {"image/jpeg": "image", "image/png": "image", "image/webp": "image", "image/gif": "image", "video/mp4": "video", "video/webm": "video", "video/quicktime": "video", "audio/mpeg": "audio", "audio/wav": "audio", "audio/webm": "audio", "audio/ogg": "audio", "audio/mp4": "audio", "audio/x-m4a": "audio"}

@app.post("/api/memories/{memory_id}/media", status_code=201)
async def upload_media(memory_id: int, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(db_session)):
    friendly_error("Media uploads are disabled in this text-only BondBook deployment.", 410)
    memory = db.get(Memory, memory_id)
    if not memory: friendly_error("Memory not found.", 404)
    if memory.owner_id != user.id: friendly_error("Only the owner can add media.", 403)
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES: friendly_error("Unsupported file type. Please use a common image, video, or audio format.")
    extension = Path(file.filename or "upload").suffix.lower()[:12]
    stored_name = f"{uuid.uuid4().hex}{extension}"
    target = UPLOAD_DIR / stored_name
    size = 0
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    output.close(); target.unlink(missing_ok=True); friendly_error(f"Files must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")
                output.write(chunk)
    except HTTPException: raise
    except Exception:
        target.unlink(missing_ok=True); friendly_error("The upload could not be saved. Please try again.", 500)
    media = Media(memory_id=memory.id, original_name=(file.filename or "upload")[:255], stored_name=stored_name, content_type=content_type, kind=ALLOWED_TYPES[content_type], size=size)
    db.add(media); db.commit(); db.refresh(media)
    return {"id": media.id, "name": media.original_name, "kind": media.kind, "content_type": media.content_type, "size": media.size, "url": f"/api/media/{media.id}"}

@app.delete("/api/media/{media_id}", status_code=204)
def delete_media(media_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    media = db.get(Media, media_id)
    if not media: friendly_error("Media not found.", 404)
    if media.memory.owner_id != user.id: friendly_error("Only the owner can delete this media.", 403)
    path = UPLOAD_DIR / media.stored_name
    if path.exists(): path.unlink()
    db.delete(media); db.commit()

@app.get("/api/media/{media_id}")
def get_media(media_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    media = db.get(Media, media_id)
    if not media or not can_view(media.memory, user): friendly_error("This file is unavailable to you.", 404)
    path = UPLOAD_DIR / media.stored_name
    if not path.is_file(): friendly_error("This media file is missing.", 404)
    return FileResponse(path, media_type=media.content_type, filename=media.original_name, content_disposition_type="inline")

@app.post("/api/reflections/{memory_id}/responses", status_code=201)
def add_response(memory_id: int, payload: ResponseInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    reflection = db.get(Memory, memory_id)
    if not reflection or not reflection.is_reflection or not can_view(reflection, user): friendly_error("That reflection is unavailable to you.", 404)
    if reflection.owner_id == user.id: friendly_error("A response is for your connected friend to add.")
    response = ReflectionResponse(reflection_id=reflection.id, author_id=user.id, message=payload.message.strip())
    db.add(response); notify(db, reflection.owner_id, "reflection_response", f"{user.name} responded to your reflection “{reflection.title}”.", reflection.id)
    db.commit(); db.refresh(response)
    return {"id": response.id, "message": response.message, "author_id": user.id, "author_name": user.name, "author_color": user.avatar_color, "created_at": response.created_at}

@app.get("/api/chat/messages")
def get_chat_messages(user: User = Depends(current_user), db: Session = Depends(db_session)):
    friend = connected_friend(user, db)
    conversation = or_(
        and_(ChatMessage.sender_id == user.id, ChatMessage.recipient_id == friend.id),
        and_(ChatMessage.sender_id == friend.id, ChatMessage.recipient_id == user.id),
    )
    messages = db.scalars(select(ChatMessage).where(conversation).order_by(ChatMessage.created_at.asc()).limit(200)).all()
    return {"friend": {"id": friend.id, "name": friend.name, "avatar_color": friend.avatar_color}, "messages": [chat_data(message, user) for message in messages]}

@app.post("/api/chat/messages", status_code=201)
def send_chat_message(payload: ChatMessageInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    friend = connected_friend(user, db)
    message_text = payload.message.strip()
    if not message_text:
        friendly_error("Write a message before sending it.")
    message = ChatMessage(sender_id=user.id, recipient_id=friend.id, message=message_text)
    db.add(message)
    notify(db, friend.id, "chat_message", f"{user.name} sent you a message.")
    db.commit(); db.refresh(message)
    return chat_data(message, user)

def letter_data(letter: OpenWhenLetter, user: User, db: Session) -> dict:
    sender = db.get(User, letter.sender_id)
    return {"id": letter.id, "title": letter.title, "occasion": letter.occasion, "content": letter.content, "visibility": letter.visibility, "is_mine": letter.sender_id == user.id, "sender_name": sender.name if sender else "Your friend", "created_at": letter.created_at}

@app.get("/api/letters")
def list_letters(user: User = Depends(current_user), db: Session = Depends(db_session)):
    sent = db.scalars(select(OpenWhenLetter).where(OpenWhenLetter.sender_id == user.id).order_by(OpenWhenLetter.created_at.desc())).all()
    received = []
    if user.friend_id:
        received = db.scalars(select(OpenWhenLetter).where(OpenWhenLetter.sender_id == user.friend_id, OpenWhenLetter.recipient_id == user.id, OpenWhenLetter.visibility == "Shared").order_by(OpenWhenLetter.created_at.desc())).all()
    return {"sent": [letter_data(letter, user, db) for letter in sent], "received": [letter_data(letter, user, db) for letter in received]}

@app.post("/api/letters", status_code=201)
def create_letter(payload: LetterInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    recipient_id = None
    if payload.visibility == "Shared":
        friend = connected_friend(user, db)
        if not payload.confirmed_share: friendly_error("Please confirm before sharing this letter.")
        recipient_id = friend.id
    letter = OpenWhenLetter(sender_id=user.id, recipient_id=recipient_id, title=payload.title.strip(), occasion=payload.occasion.strip(), content=payload.content.strip(), visibility=payload.visibility)
    db.add(letter)
    if recipient_id: notify(db, recipient_id, "open_when_letter", f"{user.name} left you an Open When letter.")
    db.commit(); db.refresh(letter)
    return letter_data(letter, user, db)

@app.delete("/api/letters/{letter_id}", status_code=204)
def delete_letter(letter_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    letter = db.get(OpenWhenLetter, letter_id)
    if not letter: friendly_error("Letter not found.", 404)
    if letter.sender_id != user.id: friendly_error("Only the author can delete this letter.", 403)
    db.delete(letter); db.commit()

def pair_game(user: User, friend: User, db: Session) -> Optional[DuoGame]:
    pair = or_(and_(DuoGame.player_one_id == user.id, DuoGame.player_two_id == friend.id), and_(DuoGame.player_one_id == friend.id, DuoGame.player_two_id == user.id))
    return db.scalar(select(DuoGame).where(pair).order_by(DuoGame.updated_at.desc()))

def game_data(game: DuoGame, user: User) -> dict:
    symbol = "X" if game.player_one_id == user.id else "O"
    return {"id": game.id, "board": game.board, "status": game.status, "turn_user_id": game.turn_user_id, "winner_id": game.winner_id, "is_my_turn": game.status == "active" and game.turn_user_id == user.id, "symbol": symbol, "is_winner": game.winner_id == user.id}

@app.get("/api/games/tic-tac-toe")
def get_game(user: User = Depends(current_user), db: Session = Depends(db_session)):
    friend = connected_friend(user, db)
    game = pair_game(user, friend, db)
    return {"game": game_data(game, user) if game else None}

@app.post("/api/games/tic-tac-toe", status_code=201)
def start_game(user: User = Depends(current_user), db: Session = Depends(db_session)):
    friend = connected_friend(user, db)
    game = pair_game(user, friend, db)
    if not game:
        game = DuoGame(player_one_id=user.id, player_two_id=friend.id, turn_user_id=user.id)
        db.add(game)
    else:
        game.board = "---------"; game.turn_user_id = user.id; game.status = "active"; game.winner_id = None
    notify(db, friend.id, "game", f"{user.name} started a Tic-Tac-Toe game with you.")
    db.commit(); db.refresh(game)
    return {"game": game_data(game, user)}

@app.post("/api/games/tic-tac-toe/{game_id}/move")
def make_game_move(game_id: int, payload: GameMoveInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    friend = connected_friend(user, db); game = db.get(DuoGame, game_id)
    if not game or pair_game(user, friend, db) != game: friendly_error("This game is unavailable.", 404)
    if game.status != "active" or game.turn_user_id != user.id: friendly_error("It is not your turn.", 409)
    board = list(game.board)
    if board[payload.position] != "-": friendly_error("Choose an empty square.", 409)
    board[payload.position] = "X" if game.player_one_id == user.id else "O"; game.board = "".join(board)
    winning_lines = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))
    won = any(board[a] == board[b] == board[c] != "-" for a,b,c in winning_lines)
    if won: game.status = "finished"; game.winner_id = user.id; notify(db, friend.id, "game", f"{user.name} won your Tic-Tac-Toe game.")
    elif "-" not in board: game.status = "finished"; game.winner_id = None; notify(db, friend.id, "game", "Your Tic-Tac-Toe game ended in a draw.")
    else: game.turn_user_id = friend.id; notify(db, friend.id, "game", f"{user.name} made a move. Your turn in Tic-Tac-Toe.")
    db.commit(); db.refresh(game)
    return {"game": game_data(game, user)}

@app.get("/api/timeline")
def timeline(user: User = Depends(current_user), db: Session = Depends(db_session)):
    visible = visible_memories_for(user)
    memories = db.scalars(select(Memory).where(visible).order_by(Memory.memory_date.asc(), Memory.created_at.asc())).all()
    return [memory_data(m, db, include_responses=False) for m in memories]

@app.get("/api/gallery")
def gallery(kind: str = "", user: User = Depends(current_user), db: Session = Depends(db_session)):
    return []
    visible = visible_memories_for(user)
    query = select(Media).join(Memory).where(visible)
    if kind: query = query.where(Media.kind == kind)
    items = db.scalars(query.order_by(Media.created_at.desc())).all()
    return [{"id": m.id, "memory_id": m.memory_id, "memory_title": m.memory.title, "owner_id": m.memory.owner_id, "name": m.original_name, "kind": m.kind, "content_type": m.content_type, "size": m.size, "created_at": m.created_at, "url": f"/api/media/{m.id}"} for m in items]

@app.get("/api/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(db_session)):
    records = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)).all()
    return [{"id": n.id, "type": n.type, "message": n.message, "memory_id": n.memory_id, "is_read": n.is_read, "created_at": n.created_at} for n in records]

@app.post("/api/notifications/read", status_code=204)
def read_notifications(user: User = Depends(current_user), db: Session = Depends(db_session)):
    for record in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.is_read == False)).all(): record.is_read = True
    db.commit()
