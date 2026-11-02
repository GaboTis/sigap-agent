FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY datos_municipio ./datos_municipio
RUN mkdir -p /app/exportes

EXPOSE 8225
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8225 --log-level info 2>&1"]
