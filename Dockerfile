# syntax=docker/dockerfile:1

FROM python:3.14.5-alpine AS builder

RUN apk add --no-cache build-base libpq-dev

COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.14.5-alpine

ARG UID=1002
ARG GID=1002

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/venv/bin:$PATH"

RUN apk add --no-cache bash libpq \
    && addgroup -g ${GID} app_user \
    && adduser -u ${UID} -G app_user -D app_user \
    && install -d -m 0755 -o app_user -g app_user /app \
    && install -d -m 0755 -o app_user -g app_user /app/static

COPY --from=builder /venv /venv
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /app
USER app_user:app_user

COPY --chown=app_user:app_user backend/ .

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
