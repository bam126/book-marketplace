import os
from service_discovery import consul_lifespan
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

# --- Настройки ---
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "catalog-default")
PORT = int(os.getenv("PORT", 8002))

# In-memory хранилище
products_db: Dict[int, dict] = {}
next_id = 1

# Модели
class ProductCreate(BaseModel):
    name: str = Field(..., description="Название товара", example="Война и мир")
    price: float = Field(..., gt=0, description="Цена товара", example=599.99)
    description: Optional[str] = Field(None, description="Описание товара")
    stock: int = Field(0, ge=0, description="Количество на складе")

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    stock: Optional[int] = Field(None, ge=0)

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    description: Optional[str]
    stock: int
    instance_id: str

class ProductsListResponse(BaseModel):
    instance_id: str
    total: int
    skip: int
    limit: int
    products: List[ProductResponse]

app = FastAPI(
    title="Catalog Service",
    description="Микросервис управления каталогом товаров",
    version="1.0.0",
    docs_url="/api/catalog/api-docs",
    openapi_url="/api/catalog/openapi.json",
    redoc_url=None,
    lifespan=consul_lifespan("catalog", 8002)
)

# Healthcheck
@app.get("/", tags=["Health"], summary="Проверка работоспособности")
@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "service": "catalog", "instance_id": INSTANCE_NAME}

# GET /api/catalog/products с пагинацией
@app.get("/api/catalog/products", response_model=ProductsListResponse, tags=["Catalog"],
         summary="Получить список товаров с пагинацией",
         description="Возвращает список товаров с поддержкой пагинации через параметры skip и limit.")
def get_products(
    skip: int = Query(0, ge=0, description="Количество пропускаемых записей"),
    limit: int = Query(10, ge=1, le=100, description="Максимальное количество записей")
):
    all_products = list(products_db.values())
    paginated = all_products[skip:skip + limit]
    return {
        "instance_id": INSTANCE_NAME,
        "total": len(all_products),
        "skip": skip,
        "limit": limit,
        "products": paginated
    }

# GET /api/catalog/products/{id}
@app.get("/api/catalog/products/{product_id}", response_model=ProductResponse, tags=["Catalog"],
         summary="Получить товар по ID",
         description="Возвращает подробную информацию о товаре по его уникальному идентификатору.")
def get_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    product = products_db[product_id].copy()
    product["instance_id"] = INSTANCE_NAME
    return product

# POST /api/catalog/products
@app.post("/api/catalog/products", response_model=ProductResponse, status_code=201, tags=["Catalog"],
          summary="Создать новый товар",
          description="Добавляет новый товар в каталог.")
def create_product(product: ProductCreate):
    global next_id
    new_product = {
        "id": next_id,
        "name": product.name,
        "price": product.price,
        "description": product.description,
        "stock": product.stock,
        "instance_id": INSTANCE_NAME
    }
    products_db[next_id] = new_product
    next_id += 1
    return new_product

# PUT /api/catalog/products/{id}
@app.put("/api/catalog/products/{product_id}", response_model=ProductResponse, tags=["Catalog"],
         summary="Обновить товар",
         description="Обновляет данные существующего товара.")
def update_product(product_id: int, product_update: ProductUpdate):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    product = products_db[product_id]
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        product[field] = value
    product["instance_id"] = INSTANCE_NAME
    return product

# DELETE /api/catalog/products/{id}
@app.delete("/api/catalog/products/{product_id}", tags=["Catalog"],
            summary="Удалить товар",
            description="Удаляет товар из каталога по ID.")
def delete_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    deleted = products_db.pop(product_id)
    return {"message": f"Товар '{deleted['name']}' удалён", "instance_id": INSTANCE_NAME}
