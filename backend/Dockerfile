FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --system app
USER app
# One worker only: live updates and per-machine locks are held in process memory.
# --forwarded-allow-ips trusts the reverse proxy in front of this container (nginx in
# docker-compose, or your host's own edge proxy, e.g. Railway) to report the real client IP.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
