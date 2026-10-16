from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
import uuid
from service_discovery import consul_lifespan

app = FastAPI(
    title="Order Service",
    description="Микросервис управления заказами пользователей",
    version="1.0.0",
    docs_url="/api/orders/api-docs",
    openapi_url="/api/orders/openapi.json",
    lifespan=consul_lifespan("order", 8004),
    redoc_url=None
)

# In-memory хранилище заказов
orders_db: Dict[str, dict] = {}

# Модели данных
class OrderItemCreate(BaseModel):
    product_id: int = Field(..., description="ID товара из Catalog-сервиса")
    quantity: int = Field(..., gt=0, description="Количество товара")

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": 1,
                "quantity": 2
            }
        }

class OrderCreate(BaseModel):
    user_id: str = Field(..., description="ID пользователя")
    items: List[OrderItemCreate] = Field(..., description="Список товаров в заказе")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user@example.com",
                "items": [
                    {"product_id": 1, "quantity": 2},
                    {"product_id": 3, "quantity": 1}
                ]
            }
        }

class OrderItemResponse(BaseModel):
    product_id: int
    quantity: int

class OrderResponse(BaseModel):
    id: str
    user_id: str
    items: List[OrderItemResponse]
    created_at: str
    status: str

# POST /api/orders — создать заказ
@app.post("/api/orders", response_model=OrderResponse, status_code=201, tags=["Orders"],
          summary="Создать новый заказ",
          description="Создаёт новый заказ для пользователя. Содержит список товаров с их количеством.")
def create_order(order: OrderCreate):
    order_id = str(uuid.uuid4())
    new_order = {
        "id": order_id,
        "user_id": order.user_id,
        "items": [{"product_id": item.product_id, "quantity": item.quantity} for item in order.items],
        "created_at": datetime.utcnow().isoformat(),
        "status": "pending"
    }
    orders_db[order_id] = new_order
    return new_order

# GET /api/orders — получить заказы пользователя
@app.get("/api/orders", response_model=List[OrderResponse], tags=["Orders"],
         summary="Получить заказы пользователя",
         description="Возвращает список всех заказов указанного пользователя.")
def get_orders_by_user(
    user_id: str = Query(..., description="ID пользователя (email)")
):
    user_orders = [order for order in orders_db.values() if order["user_id"] == user_id]
    if not user_orders:
        raise HTTPException(status_code=404, detail=f"Заказы для пользователя {user_id} не найдены")
    return user_orders

# GET /api/orders/{order_id} — получить заказ по ID
@app.get("/api/orders/{order_id}", response_model=OrderResponse, tags=["Orders"],
         summary="Получить заказ по ID",
         description="Возвращает подробную информацию о заказе по его уникальному идентификатору.")
def get_order(order_id: str):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return orders_db[order_id]

@app.get("/health", tags=["Health"])
@app.get("/", tags=["Health"], include_in_schema=False)
def health():
    return {"status": "healthy", "service": "order"}
