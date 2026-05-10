from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("DEPLOYER_HOST_BIND", "0.0.0.0")
    port = int(os.getenv("DEPLOYER_PORT", "8000"))
    uvicorn.run("deployer.api:app", host=host, port=port)


if __name__ == "__main__":
    main()
