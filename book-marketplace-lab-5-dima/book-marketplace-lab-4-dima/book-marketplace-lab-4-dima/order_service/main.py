from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
import uuid
import json
import pika
import threading
import os

# Импорт consul_lifespan оставлен, если он у вас работает. 
# Если нет - удалите эту строку и аргумент lifespan в FastAPI
try:
    from service_discovery import consul_lifespan
    HAS_CONSUL = True
except ImportError:
    HAS_CONSUL = False

app = FastAPI(
    title="Order Service",
    description="Микросервис управления заказами пользователей (ЛР4: с асинхронной интеграцией)",
    version="1.0.0",
    docs_url="/api/orders/api-docs",
    openapi_url="/api/orders/openapi.json",
    redoc_url=None,
    **( {"lifespan": consul_lifespan("order", 8004)} if HAS_CONSUL else {} )
)

# ==========================================
# 1. НАСТРОЙКА RABBITMQ (ЛР4)
# ==========================================
CLOUDAMQP_URL = os.getenv(
    "CLOUDAMQP_URL",
    "amqps://lwkugnkt:XKCO1a6rcY_oxvr5KzPLnYXVzOfx1lVv@hawk.rmq.cloudamqp.com/lwkugnkt"
)

try:
    # Парсим URL для pika
    parameters = pika.URLParameters(CLOUDAMQP_URL)
    rabbitmq_connection = pika.BlockingConnection(parameters)
    rabbitmq_channel = rabbitmq_connection.channel()
    
    # Объявляем очереди
    rabbitmq_channel.queue_declare(queue='order_created', durable=True)
    rabbitmq_channel.queue_declare(queue='payment_completed', durable=True)
    rabbitmq_channel.queue_declare(queue='payment_failed', durable=True)
    rabbitmq_channel.queue_declare(queue='order_cancelled', durable=True)
    
    print("✅ Успешное подключение к CloudAMQP")
    
except Exception as e:
    print(f" Не удалось подключиться к CloudAMQP: {e}")
    rabbitmq_channel = None

# ==========================================
# 2. МОДЕЛИ ДАННЫХ
# ==========================================
class OrderItemCreate(BaseModel):
    product_id: int = Field(..., description="ID товара из Catalog-сервиса")
    quantity: int = Field(..., gt=0, description="Количество товара")

class OrderCreate(BaseModel):
    user_id: str = Field(..., description="ID пользователя")
    items: List[OrderItemCreate] = Field(..., description="Список товаров в заказе")
    total_amount: float = Field(..., description="Общая сумма заказа") # Добавлено для ЛР4

class OrderItemResponse(BaseModel):
    product_id: int
    quantity: int

class OrderResponse(BaseModel):
    id: str
    user_id: str
    items: List[OrderItemResponse]
    total_amount: float
    created_at: str
    status: str  # PENDING, CONFIRMED, CANCELLED

# In-memory хранилище заказов
orders_db: Dict[str, dict] = {}

# ==========================================
# 3. ОБРАБОТЧИКИ СОБЫТИЙ ОТ PAYMENT SERVICE (ЛР4)
# ==========================================
def on_payment_completed(ch, method, properties, body):
    event = json.loads(body)
    order_id = event['orderId']
    
    # Идемпотентность: меняем статус только если он ещё PENDING
    if order_id in orders_db and orders_db[order_id]["status"] == "PENDING":
        orders_db[order_id]["status"] = "CONFIRMED"
        print(f"✅ [Order Service] Заказ {order_id} подтверждён (оплата прошла успешно)")

def on_payment_failed(ch, method, properties, body):
    event = json.loads(body)
    order_id = event['orderId']
    reason = event.get('reason', 'Unknown error')
    
    # КОМПЕНСАЦИЯ: меняем статус на CANCELLED
    if order_id in orders_db and orders_db[order_id]["status"] == "PENDING":
        orders_db[order_id]["status"] = "CANCELLED"
        print(f" [Order Service] Заказ {order_id} ОТМЕНЁН (компенсация). Причина: {reason}")
        
        # Публикуем событие OrderCancelled для Notification Service
        if rabbitmq_channel:
            cancel_event = {
                "orderId": order_id,
                "userId": orders_db[order_id]["user_id"],
                "reason": reason
            }
            rabbitmq_channel.basic_publish(
                exchange='',
                routing_key='order_cancelled',
                body=json.dumps(cancel_event),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"📤 [Order Service] Опубликовано событие OrderCancelled для заказа {order_id}")

# Запуск потребления сообщений в фоновом потоке (чтобы не блокировать FastAPI)
if rabbitmq_channel:
    rabbitmq_channel.basic_consume(
        queue='payment_completed',
        on_message_callback=on_payment_completed,
        auto_ack=True
    )
    rabbitmq_channel.basic_consume(
        queue='payment_failed',
        on_message_callback=on_payment_failed,
        auto_ack=True
    )
    
    def start_consuming():
        print("📡 [Order Service] Подписан на очереди payment_completed и payment_failed...")
        rabbitmq_channel.start_consuming()

    consumer_thread = threading.Thread(target=start_consuming, daemon=True)
    consumer_thread.start()

# ==========================================
# 4. REST ENDPOINTS
# ==========================================
@app.post("/api/orders", response_model=OrderResponse, status_code=201, tags=["Orders"],
          summary="Создать новый заказ",
          description="Создаёт новый заказ и публикует событие OrderCreated в брокер.")
def create_order(order: OrderCreate):
    order_id = str(uuid.uuid4())
    new_order = {
        "id": order_id,
        "user_id": order.user_id,
        "items": [{"product_id": item.product_id, "quantity": item.quantity} for item in order.items],
        "total_amount": order.total_amount,
        "created_at": datetime.utcnow().isoformat(),
        "status": "PENDING" # Начальный статус
    }
    orders_db[order_id] = new_order
    
    # ПУБЛИКАЦИЯ СОБЫТИЯ OrderCreated (ЛР4)
    if rabbitmq_channel:
        event_payload = {
            "orderId": order_id,
            "userId": order.user_id,
            "items": [{"productId": item.product_id, "quantity": item.quantity} for item in order.items],
            "totalAmount": order.total_amount,
            "createdAt": new_order["created_at"]
        }
        rabbitmq_channel.basic_publish(
            exchange='',
            routing_key='order_created',
            body=json.dumps(event_payload),
            properties=pika.BasicProperties(delivery_mode=2) # persistent
        )
        print(f" [Order Service] Опубликовано событие OrderCreated: {order_id}")
    else:
        print(f" [Order Service] Заказ {order_id} создан, но RabbitMQ недоступен, событие не отправлено.")
    
    return new_order

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

@app.get("/api/orders/{order_id}", response_model=OrderResponse, tags=["Orders"],
         summary="Получить заказ по ID",
         description="Возвращает подробную информацию о заказе по его уникальному идентификатору.")
def get_order(order_id: str):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return orders_db[order_id]

@app.get("/health", tags=["Health"], include_in_schema=False)
@app.get("/", tags=["Health"], include_in_schema=False)
def health():
    return {"status": "healthy", "service": "order"}