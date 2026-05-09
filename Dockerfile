FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["python", "-m", "deployer.server"]
