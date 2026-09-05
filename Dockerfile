FROM python:3.14-alpine AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.14-alpine

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SELFSEND_HOST=0.0.0.0 \
    SELFSEND_PORT=8787

RUN addgroup -S selfsend && adduser -S -G selfsend selfsend

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=selfsend:selfsend app ./app
COPY --chown=selfsend:selfsend run.py ./

USER selfsend

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${SELFSEND_PORT}/health" || exit 1

CMD ["python", "run.py"]
