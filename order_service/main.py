from contextlib import asynccontextmanager
import asyncio
import json
import uuid
from typing import List, Literal
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from service_discovery import consul_lifespan
from messaging import Worker, database, transaction, initialize, enqueue, now, log

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)

class OrderCreate(BaseModel):
    user_id: str
    items: List[OrderItemCreate] = Field(..., min_length=1)
    # Defaults preserve the request format used in LR3.
    total_amount: float = Field(0, ge=0)
    payment_outcome: Literal["success", "fail"] = "success"

class OrderItemResponse(BaseModel):
    product_id: int
    quantity: int

class OrderResponse(BaseModel):
    id: str
    user_id: str
    items: List[OrderItemResponse]
    total_amount: float
    created_at: str
    status: str
    event_delivery: str

def payment_result(db, event):
    order_id = event["orderId"]
    row = db.execute("SELECT body,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise ValueError("Unknown order")
    if row["status"] != "PENDING":
        return "DUPLICATE result ignored; status=" + row["status"]
    order = json.loads(row["body"])
    if event["eventType"] == "PaymentCompleted":
        status = "CONFIRMED"
    else:
        status = "CANCELLED"
        enqueue(db, "OrderCancelled", order_id, userId=order["user_id"], reason=event.get("reason", "Payment failed"))
    db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    return "STATE PENDING -> " + status + ("; COMPENSATION OrderCancelled queued" if status == "CANCELLED" else "")

worker = Worker("order.payments", payment_result)

@asynccontextmanager
async def lifespan(app):
    initialize()
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,body TEXT NOT NULL,status TEXT NOT NULL)")
        db.commit()
    worker.start()
    async with consul_lifespan("order", 8004)(app):
        try:
            yield
        finally:
            await asyncio.to_thread(worker.stop)

app = FastAPI(title="Order Service", description="Заказы и Saga через RabbitMQ", version="1.0.0",
    docs_url="/api/orders/api-docs", openapi_url="/api/orders/openapi.json", redoc_url=None, lifespan=lifespan)

def response(db, row):
    order = json.loads(row["body"])
    order["status"] = row["status"]
    pending = db.execute("SELECT 1 FROM outbox WHERE order_id=? AND event_type='OrderCreated' AND sent_at IS NULL", (order["id"],)).fetchone()
    order["event_delivery"] = "QUEUED" if pending else "PUBLISHED"
    return order

@app.post("/api/orders", response_model=OrderResponse, status_code=201, tags=["Orders"], summary="Создать заказ")
def create_order(order: OrderCreate):
    order_id = str(uuid.uuid4())
    new_order = {"id": order_id, "user_id": order.user_id,
        "items": [item.model_dump() for item in order.items], "total_amount": order.total_amount,
        "created_at": now(), "status": "PENDING"}
    with transaction() as db:
        db.execute("INSERT INTO orders VALUES(?,?,?)", (order_id, json.dumps(new_order), "PENDING"))
        enqueue(db, "OrderCreated", order_id, userId=order.user_id,
            items=[{"productId": item.product_id, "quantity": item.quantity} for item in order.items],
            totalAmount=order.total_amount, paymentOutcome=order.payment_outcome, createdAt=new_order["created_at"])
    log.info("CREATED status=PENDING; OrderCreated QUEUED in SQLite orderId=%s", order_id)
    return {**new_order, "event_delivery": "QUEUED"}

@app.get("/api/orders", response_model=List[OrderResponse], tags=["Orders"])
def get_orders_by_user(user_id: str = Query(...)):
    with database() as db:
        rows = db.execute("SELECT * FROM orders ORDER BY rowid").fetchall()
        orders = [response(db, row) for row in rows if json.loads(row["body"])["user_id"] == user_id]
    if not orders:
        raise HTTPException(status_code=404, detail="Заказы пользователя не найдены")
    return orders

@app.get("/api/orders/{order_id}", response_model=OrderResponse, tags=["Orders"])
def get_order(order_id: str):
    with database() as db:
        row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        return response(db, row)

@app.get("/health", tags=["Health"])
@app.get("/", include_in_schema=False)
def health():
    return {"status": "healthy", "service": "order", "broker": "connected" if worker.connected.is_set() else "retrying"}
