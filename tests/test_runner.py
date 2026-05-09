from deployer.errors import CommandError
from deployer.runner import CommandRunner


def test_runner_success(tmp_path):
    result = CommandRunner().run(["/bin/sh", "-c", "printf ok"], cwd=tmp_path)

    assert result.returncode == 0
    assert result.output == "ok"


def test_runner_failure(tmp_path):
    try:
        CommandRunner().run(["/bin/sh", "-c", "printf bad && exit 7"], cwd=tmp_path)
    except CommandError as exc:
        assert exc.returncode == 7
        assert exc.output == "bad"
    else:
        raise AssertionError("CommandError was not raised")
