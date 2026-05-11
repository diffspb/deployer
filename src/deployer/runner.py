from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
import os
from pathlib import Path

from deployer.errors import CommandError


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    output: str


class CommandRunner:
    def run(self, args: Sequence[str], cwd: Path, env: dict[str, str] | None = None) -> CommandResult:
        process_env = None
        if env:
            process_env = {**os.environ, **env}
        process = subprocess.run(
            list(args),
            cwd=cwd,
            env=process_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        result = CommandResult(tuple(args), process.returncode, process.stdout)
        if result.returncode != 0:
            raise CommandError(
                f"Command failed with exit code {result.returncode}: {' '.join(args)}",
                result.returncode,
                result.output,
            )
        return result
