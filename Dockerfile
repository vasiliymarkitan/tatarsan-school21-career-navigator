FROM python:3.11-slim

WORKDIR /app

COPY requirements_web.txt .
RUN pip install --no-cache-dir -r requirements_web.txt

COPY api_server.py .
COPY parser/ parser/
COPY ai/ ai/
COPY web/ web/

EXPOSE 8000

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
