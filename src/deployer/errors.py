class DeployerError(Exception):
    """Base exception for user-facing deployer failures."""


class ManifestError(DeployerError):
    """Raised when deployer.yml is missing or invalid."""


class CommandError(DeployerError):
    """Raised when an external command fails."""

    def __init__(self, message: str, returncode: int, output: str):
        super().__init__(message)
        self.returncode = returncode
        self.output = output
