FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8005
WORKDIR /app
COPY graphql_gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY graphql_gateway/main.py ./main.py
COPY service_discovery.py ./service_discovery.py
RUN useradd --uid 10001 --create-home appuser
USER appuser
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"$PORT\""]
