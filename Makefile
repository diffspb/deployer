PYTHON = .venv/bin/python
PIP = .venv/bin/pip

.PHONY: venv install test coverage validate-samples render-tasktrack render-cpucol clean

venv:
	python3 -m venv .venv

install: venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov=deployer --cov-report=term-missing

validate-samples:
	$(PYTHON) -m deployer.cli validate /home/sanek/projects/claudecode/tasktrack_project --manifest docs/sample-manifests/tasktrack.deployer.yml
	$(PYTHON) -m deployer.cli validate /home/sanek/projects/claudecode/test_proj --manifest docs/sample-manifests/cpucol.deployer.yml

render-tasktrack:
	$(PYTHON) -m deployer.cli render-override /home/sanek/projects/claudecode/tasktrack_project --manifest docs/sample-manifests/tasktrack.deployer.yml

render-cpucol:
	$(PYTHON) -m deployer.cli render-override /home/sanek/projects/claudecode/test_proj --manifest docs/sample-manifests/cpucol.deployer.yml

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
