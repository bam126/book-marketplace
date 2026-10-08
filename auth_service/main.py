# pip install fastapi uvicorn
# pip install passlib[bcrypt] PyJWT python-multipart
# uvicorn main:app --reload --port 8001
# http://127.0.0.1:8001/docs


from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime, timedelta
import jwt
import hashlib
import os
from service_discovery import consul_lifespan

app = FastAPI(title="Auth Service", lifespan=consul_lifespan("auth", 8001))


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "service": "auth"}


SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-for-lab")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Имитация базы данных в памяти
fake_users_db: Dict[str, dict] = {}

# Модели данных
class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

# Хэширование через SHA-256 (надежно и без лишних зависимостей)
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

# Генерация JWT токена
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Инициализация схемы безопасности для Swagger UI
security = HTTPBearer()

# 1. Регистрация
@app.post("/register", tags=["Auth"])
def register(user: UserRegister):
    if user.username in fake_users_db:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    
    hashed_password = hash_password(user.password)
    fake_users_db[user.username] = {
        "username": user.username,
        "password": hashed_password
    }
    return {"message": "Пользователь успешно зарегистрирован"}

# 2. Вход
@app.post("/login", tags=["Auth"])
def login(user: UserLogin):
    db_user = fake_users_db.get(user.username)
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    return {"message": "Успешный вход", "token": access_token}

# 3. Защищенный эндпоинт
@app.get("/me", tags=["Auth"])
def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Невалидный токен")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Невалидный токен")
    
    return {"username": username, "message": "Это защищенные данные пользователя"}
