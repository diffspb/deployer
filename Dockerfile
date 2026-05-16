FROM docker:29-cli AS docker-cli

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx

COPY pyproject.toml README.md ./
COPY src ./src

ARG DEPLOYER_BUILD_COMMIT=unknown
ARG DEPLOYER_BUILD_DATE=unknown
RUN printf '{"commit":"%s","date":"%s"}\n' "$DEPLOYER_BUILD_COMMIT" "$DEPLOYER_BUILD_DATE" > /app/build-info.json

RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app/src \
    DEPLOYER_STATE_DB=/var/lib/deployer/state.db \
    DEPLOYER_RUNTIME_DIR=/var/lib/deployer \
    DOCKER_BUILDKIT=1 \
    COMPOSE_DOCKER_CLI_BUILD=1
EXPOSE 8000

CMD ["python", "-m", "deployer.server"]
