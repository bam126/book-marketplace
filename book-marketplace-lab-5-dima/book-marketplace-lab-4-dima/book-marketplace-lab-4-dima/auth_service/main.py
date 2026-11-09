# pip install fastapi uvicorn
# Dependencies: auth_service/requirements.txt
# From project root: uvicorn auth_service.main:app --port 8001
# http://127.0.0.1:8080/api/auth/api-docs

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Dict, Optional
from datetime import datetime, timedelta
import jwt
from passlib.hash import pbkdf2_sha256
import os
from service_discovery import consul_lifespan

app = FastAPI(
    title="Auth Service",
    description="Микросервис аутентификации и управления пользователями",
    version="1.0.0",
    docs_url="/api/auth/api-docs",
    openapi_url="/api/auth/openapi.json",
    lifespan=consul_lifespan("auth", 8001),
    redoc_url=None
)

# Настройки JWT
SECRET_KEY = os.environ["SECRET_KEY"]
if len(SECRET_KEY.encode()) < 32 or SECRET_KEY.startswith("REPLACE_"):
    raise RuntimeError("Set SECRET_KEY to a random secret of at least 32 bytes")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# In-memory хранилище
fake_users_db: Dict[str, dict] = {}

# Модели данных
class UserRegister(BaseModel):
    email: str
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "securepass123"
            }
        }

class UserLogin(BaseModel):
    email: str
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "securepass123"
            }
        }

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    message: str

class UserResponse(BaseModel):
    email: str
    message: str

# Passlib: соль и PBKDF2-SHA256 вместо одиночного SHA-256.
def hash_password(password: str) -> str:
    return pbkdf2_sha256.using(rounds=600_000).hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pbkdf2_sha256.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

security = HTTPBearer()

# Регистрация: POST /api/auth/register
@app.post("/api/auth/register", response_model=UserResponse, tags=["Auth"],
          summary="Регистрация нового пользователя",
          description="Создаёт нового пользователя в системе. Email должен быть уникальным.")
def register(user: UserRegister):
    if user.email in fake_users_db:
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")

    fake_users_db[user.email] = {
        "email": user.email,
        "password": hash_password(user.password)
    }
    return {"email": user.email, "message": "Пользователь успешно зарегистрирован"}

# Вход: POST /api/auth/login
@app.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"],
          summary="Аутентификация пользователя",
          description="Проверяет учётные данные и возвращает JWT-токен.")
def login(user: UserLogin):
    db_user = fake_users_db.get(user.email)
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer", "message": "Успешный вход"}

# Защищённый эндпоинт: GET /api/auth/me
@app.get("/api/auth/me", response_model=UserResponse, tags=["Auth"],
         summary="Получить данные текущего пользователя",
         description="Возвращает информацию о пользователе. Требует валидный JWT-токен в заголовке Authorization.")
def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Невалидный токен")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Невалидный токен")

    return {"email": email, "message": "Это защищённые данные пользователя"}

@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "service": "auth"}
