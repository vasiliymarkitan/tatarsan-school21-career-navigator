FROM python:3.11-slim

WORKDIR /app

COPY requirements_web.txt .
RUN pip install --no-cache-dir -r requirements_web.txt

COPY api_server.py auth_utils.py ./
COPY parser/ parser/
COPY ai/ ai/
COPY digest/ digest/
COPY web/ web/

RUN mkdir -p /app/data

EXPOSE 8000

# One worker: in-memory vacancy cache and digest scheduler stay consistent.
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
