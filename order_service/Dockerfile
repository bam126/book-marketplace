FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8004
WORKDIR /app
COPY order_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY order_service/main.py ./main.py
COPY service_discovery.py ./service_discovery.py
COPY messaging.py ./messaging.py
RUN mkdir -p /data && chown 10001:10001 /data
RUN useradd --uid 10001 --create-home appuser
USER appuser
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"$PORT\""]
