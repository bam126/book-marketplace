from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

app = FastAPI(
    title="Catalog Service",
    description="Микросервис управления каталогом товаров",
    version="1.0.0",
    docs_url="/api-docs"
)

products_db: Dict[int, dict] = {}
next_id = 1

class ProductCreate(BaseModel):
    name: str
    price: float
    description: Optional[str] = None
    stock: int = 0

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    stock: Optional[int] = None

@app.get("/", tags=["Health"])
def health():
    return {"status": "healthy", "service": "catalog"}

@app.get("/api/catalog/products", tags=["Catalog"])
def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
):
    all_products = list(products_db.values())
    return {
        "total": len(all_products),
        "skip": skip,
        "limit": limit,
        "products": all_products[skip:skip + limit]
    }

@app.get("/api/catalog/products/{product_id}", tags=["Catalog"])
def get_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return products_db[product_id]

@app.post("/api/catalog/products", status_code=201, tags=["Catalog"])
def create_product(product: ProductCreate):
    global next_id
    new_product = {
        "id": next_id,
        "name": product.name,
        "price": product.price,
        "description": product.description,
        "stock": product.stock
    }
    products_db[next_id] = new_product
    next_id += 1
    return new_product

@app.put("/api/catalog/products/{product_id}", tags=["Catalog"])
def update_product(product_id: int, product_update: ProductUpdate):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    product = products_db[product_id]
    update_data = product_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        product[field] = value
    return product

@app.delete("/api/catalog/products/{product_id}", tags=["Catalog"])
def delete_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    deleted = products_db.pop(product_id)
    return {"message": f"Товар '{deleted['name']}' удалён"}