FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8002
WORKDIR /app
COPY catalog_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY catalog_service/main.py ./main.py
RUN useradd --uid 10001 --create-home appuser
USER appuser
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"$PORT\""]
