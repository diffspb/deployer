from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from deployer.catalog import DEFAULT_RUNTIME_DIR


DEFAULT_STATE_DB = Path("/var/lib/deployer/state.db")


@dataclass(frozen=True)
class DeployerConfig:
    state_db: Path
    runtime_dir: Path


def load_config() -> DeployerConfig:
    return DeployerConfig(
        state_db=Path(os.getenv("DEPLOYER_STATE_DB", str(DEFAULT_STATE_DB))),
        runtime_dir=Path(os.getenv("DEPLOYER_RUNTIME_DIR", str(DEFAULT_RUNTIME_DIR))),
    )
