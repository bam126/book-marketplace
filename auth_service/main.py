# pip install fastapi uvicorn
# pip install passlib[bcrypt] PyJWT python-multipart
# uvicorn main:app --reload --port 8001
# http://127.0.0.1:8001/docs
#  http://127.0.0.1:8002/api-docs

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Dict, Optional
from datetime import datetime, timedelta
import jwt
import hashlib
import os

app = FastAPI(
    title="Auth Service",
    description="Микросервис аутентификации и управления пользователями",
    version="1.0.0",
    docs_url="/api-docs",  # Swagger UI доступен по /api-docs
    redoc_url=None
)

# Настройки JWT
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-for-lab")
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

# Хэширование паролей через SHA-256
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

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