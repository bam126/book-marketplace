FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

COPY payment_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY payment_service/main.py ./payment_service/main.py
COPY payment_service/gRPC_server.py ./payment_service/gRPC_server.py
COPY messaging.py ./messaging.py

COPY contracts/payment.proto ./contracts/payment.proto
COPY contracts/__init__.py ./contracts/__init__.py

RUN python -m grpc_tools.protoc -I. \
    --python_out=. \
    --grpc_python_out=. \
    contracts/payment.proto

RUN useradd --uid 10001 --create-home appuser \
    && mkdir /data \
    && chown 10001:10001 /data

USER appuser

CMD ["python", "-m", "payment_service.main"]