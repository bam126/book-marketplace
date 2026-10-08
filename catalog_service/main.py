# uvicorn main:app --reload --port 8002
# http://127.0.0.1:8002/docs
#  http://127.0.0.1:8003/docs

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import os
import uvicorn

app = FastAPI(title="Catalog Service")

# Получаем instance_id из переменной окружения (или значение по умолчанию)
INSTANCE_ID = os.getenv("INSTANCE_NAME", "catalog-default")

# In-memory хранилище товаров (словарь: id -> товар)
products_db: Dict[int, dict] = {}
next_id = 1  # Счётчик для автоинкремента ID

# Модель данных товара
class Product(BaseModel):
    title: str
    author: str
    price: float
    description: Optional[str] = None
    stock: int = 0

class ProductUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    stock: Optional[int] = None


# 0. Healthcheck + информация об инстансе
@app.get("/", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "service": "catalog-service",
        "instance_id": INSTANCE_ID
    }


# 1. Получить список всех товаров (GET)
@app.get("/products", tags=["Products"])
def get_products():
    return {
        "instance_id": INSTANCE_ID,
        "products": list(products_db.values())
    }


# 2. Получить товар по ID (GET)
@app.get("/products/{product_id}", tags=["Products"])
def get_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    product = products_db[product_id].copy()
    product["instance_id"] = INSTANCE_ID
    return product


# 3. Создать новый товар (POST)
@app.post("/products", status_code=201, tags=["Products"])
def create_product(product: Product):
    global next_id
    
    new_product = {
        "id": next_id,
        "title": product.title,
        "author": product.author,
        "price": product.price,
        "description": product.description,
        "stock": product.stock,
        "instance_id": INSTANCE_ID
    }
    
    products_db[next_id] = new_product
    next_id += 1
    
    return new_product


# 4. Обновить товар (PUT)
@app.put("/products/{product_id}", tags=["Products"])
def update_product(product_id: int, product_update: ProductUpdate):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    product = products_db[product_id]
    update_data = product_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        product[field] = value
    
    product["instance_id"] = INSTANCE_ID
    return product


# 5. Удалить товар (DELETE)
@app.delete("/products/{product_id}", tags=["Products"])
def delete_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    deleted_product = products_db.pop(product_id)
    return {
        "message": f"Товар '{deleted_product['title']}' успешно удалён",
        "instance_id": INSTANCE_ID
    }


# Запуск сервиса (для прямого запуска через python main.py)
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)