FROM grafana/k6:0.51.0 AS k6bin

FROM python:3.12-slim

WORKDIR /app

COPY --from=k6bin /usr/bin/k6 /usr/local/bin/k6
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY k6 ./k6

ENV PORT=8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "1200", "main:app"]
