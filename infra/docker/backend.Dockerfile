FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/README.md /app/backend/README.md
COPY backend/src /app/backend/src

RUN pip install --no-cache-dir -e .

CMD ["uvicorn", "snipebot.main:app", "--host", "0.0.0.0", "--port", "8000"]
