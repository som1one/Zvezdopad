FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel --default-timeout=300 && \
    pip install --no-cache-dir \
    --default-timeout=300 \
    --retries=5 \
    -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

