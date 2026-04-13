FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY afrilux_sav/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY afrilux_sav/ /app/
RUN chmod +x /app/entrypoint.sh /app/deploy/*.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["/app/deploy/start-web.sh"]
