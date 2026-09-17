FROM python:3.12-slim

ENV UV_PYTHON=/usr/local/bin/python
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY dags ./dags

RUN uv sync --frozen

ENV AIRFLOW__CORE__DAGS_FOLDER=/app/dags
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "airflow", "standalone"]