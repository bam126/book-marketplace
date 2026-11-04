FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8004 \
    PAYMENT_GRPC_ADDRESS=payment:50051

WORKDIR /app

COPY order_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY order_service/main.py ./main.py
COPY service_discovery.py ./service_discovery.py
COPY messaging.py ./messaging.py

COPY payment_client.py ./payment_client.py
COPY payment_breaker.py ./payment_breaker.py
COPY contracts/payment.proto ./contracts/payment.proto
COPY contracts/__init__.py ./contracts/__init__.py

RUN python -m grpc_tools.protoc -I. \
    --python_out=. \
    --grpc_python_out=. \
    contracts/payment.proto

RUN useradd --uid 10001 --create-home appuser
RUN mkdir -p /data && chown 10001:10001 /data

USER appuser

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"$PORT\""]