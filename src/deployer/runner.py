from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from deployer.errors import CommandError


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    output: str


class CommandRunner:
    def run(self, args: Sequence[str], cwd: Path) -> CommandResult:
        process = subprocess.run(
            list(args),
            cwd=cwd,
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
