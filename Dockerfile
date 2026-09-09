FROM python:3.12-slim-bookworm AS builder

RUN python -m venv /opt/request-me
ENV PATH="/opt/request-me/bin:${PATH}"

COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm

ENV PATH="/opt/request-me/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REQUEST_ME_HOST=0.0.0.0 \
    REQUEST_ME_PORT=8080

WORKDIR /app
COPY --from=builder /opt/request-me /opt/request-me
COPY server /app/server

RUN useradd --create-home --uid 10001 request-me \
    && chown -R request-me:request-me /app

USER request-me
EXPOSE 8080

CMD ["python", "-m", "server"]
