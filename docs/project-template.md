# Project Template

Use this document instead of a project generator script.

## Minimal Files

```text
.
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── deployer.yml
├── .env.prod.example
└── app/
```

## Minimal `docker-compose.yml`

```yaml
services:
  app:
    build: .
    restart: unless-stopped
    networks:
      - traefik-public

networks:
  traefik-public:
    external: true
```

## Minimal `docker-compose.prod.yml`

```yaml
services:
  app:
    env_file: .env.prod
```

## Minimal `deployer.yml`

```yaml
name: myapp
service: app
port: 8000
compose:
  files:
    - docker-compose.yml
    - docker-compose.prod.yml
env_file: .env.prod
routes:
  - host: myapp.busypage.ru
    auth: sso
healthcheck:
  path: /health
```

## Sample Agent Prompt

```text
Create a deployable FastAPI project for my personal PaaS.

Follow this contract:
- Python 3.12.
- FastAPI app with GET /health returning {"status": "ok"}.
- Dockerfile that runs uvicorn on 0.0.0.0:8000.
- docker-compose.yml with service app, restart unless-stopped, and external network traefik-public.
- docker-compose.prod.yml with env_file .env.prod and no Traefik labels.
- deployer.yml with name <PROJECT>, service app, port 8000, compose files docker-compose.yml and docker-compose.prod.yml, host <PROJECT>.busypage.ru, auth sso, healthcheck /health.
- Do not add Traefik labels manually; deployer will generate them.
- Do not create a custom user system.
- Keep app-specific secrets in .env.prod, provide .env.prod.example.

Also add tests for the app behavior.
```
