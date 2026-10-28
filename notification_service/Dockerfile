FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY notification_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY notification_service/main.py ./main.py
COPY messaging.py ./messaging.py
RUN useradd --uid 10001 --create-home appuser && mkdir /data && chown 10001:10001 /data
USER appuser
CMD ["python", "main.py"]
