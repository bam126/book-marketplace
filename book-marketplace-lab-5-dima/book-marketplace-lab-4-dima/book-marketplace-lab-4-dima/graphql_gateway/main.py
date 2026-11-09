import os
import strawberry
from service_discovery import consul_lifespan
import httpx
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
from typing import List, Optional

# --- Базовые URL REST-сервисов ---
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://127.0.0.1:8004").rstrip("/")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://127.0.0.1:8002").rstrip("/")

# --- GraphQL типы ---

@strawberry.type(description="Товар из каталога")
class Product:
    id: int = strawberry.field(description="Уникальный идентификатор товара")
    name: str = strawberry.field(description="Название товара")
    price: float = strawberry.field(description="Цена товара")
    description: Optional[str] = strawberry.field(description="Описание товара", default=None)
    stock: int = strawberry.field(description="Количество на складе", default=0)

@strawberry.type(description="Позиция в заказе")
class OrderItem:
    product_id: int = strawberry.field(description="ID товара из Catalog")
    quantity: int = strawberry.field(description="Количество единиц товара")
    product: Product = strawberry.field(description="Детали товара из Catalog-сервиса")

@strawberry.type(description="Заказ пользователя")
class Order:
    id: str = strawberry.field(description="Уникальный идентификатор заказа")
    user_id: str = strawberry.field(description="ID пользователя (email)")
    created_at: str = strawberry.field(description="Дата и время создания заказа")
    status: str = strawberry.field(description="Статус заказа")
    items: List[OrderItem] = strawberry.field(description="Список позиций в заказе")

# --- Вспомогательные функции ---

async def get_orders_by_user_id(user_id: str) -> List[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{ORDER_SERVICE_URL}/api/orders",
            params={"user_id": user_id}
        )
        response.raise_for_status()
        return response.json()

async def get_product_by_id(product_id: int) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{CATALOG_SERVICE_URL}/api/catalog/products/{product_id}"
        )
        response.raise_for_status()
        return response.json()

# --- Резолверы ---

async def resolve_orders_by_user_id(user_id: str) -> List[Order]:
    raw_orders = await get_orders_by_user_id(user_id)

    orders = []
    for raw_order in raw_orders:
        order_items = []
        for item in raw_order["items"]:
            product_data = await get_product_by_id(item["product_id"])

            order_item = OrderItem(
                product_id=item["product_id"],
                quantity=item["quantity"],
                product=Product(
                    id=product_data["id"],
                    name=product_data["name"],
                    price=product_data["price"],
                    description=product_data.get("description"),
                    stock=product_data.get("stock", 0)
                )
            )
            order_items.append(order_item)

        order = Order(
            id=raw_order["id"],
            user_id=raw_order["user_id"],
            created_at=raw_order["created_at"],
            status=raw_order["status"],
            items=order_items
        )
        orders.append(order)

    return orders

# --- GraphQL Query ---

@strawberry.type(description="Корневой тип запросов GraphQL Gateway")
class Query:
    orders_by_user_id: List[Order] = strawberry.field(
        resolver=resolve_orders_by_user_id,
        description="Получить все заказы пользователя с деталями товаров из Catalog-сервиса"
    )

# --- Создаём схему и FastAPI приложение ---


schema = strawberry.Schema(query=Query)

graphql_app = GraphQLRouter(schema)

app = FastAPI(
    title="GraphQL Gateway",
    description="API Gateway на GraphQL",
    version="1.0.0",
    docs_url=None, redoc_url=None, openapi_url=None,
    lifespan=consul_lifespan("graphql", 8005)
)

app.include_router(graphql_app, prefix="/graphql")

@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "service": "graphql-gateway"}
