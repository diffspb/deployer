PYTHON = .venv/bin/python
PIP = .venv/bin/pip
DEV_STATE_DB ?= .deployer/state.db
DEV_RUNTIME_DIR ?= .deployer/runtime
TEST_STATE_DB ?= /tmp/deployer-state.sqlite3
TEST_RUNTIME_DIR ?= /tmp/deployer-runtime

.PHONY: venv install test coverage api validate-samples render-tasktrack render-cpucol docker-build reset-dev reset-test clean

venv:
	python3 -m venv .venv

install: venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov=deployer --cov-report=term-missing

api:
	$(PYTHON) -m deployer.server

validate-samples:
	$(PYTHON) -m deployer.cli validate /home/sanek/projects/claudecode/tasktrack_project --manifest docs/sample-manifests/tasktrack.deployer.yml
	$(PYTHON) -m deployer.cli validate /home/sanek/projects/claudecode/test_proj --manifest docs/sample-manifests/cpucol.deployer.yml

render-tasktrack:
	$(PYTHON) -m deployer.cli render-override /home/sanek/projects/claudecode/tasktrack_project --manifest docs/sample-manifests/tasktrack.deployer.yml

render-cpucol:
	$(PYTHON) -m deployer.cli render-override /home/sanek/projects/claudecode/test_proj --manifest docs/sample-manifests/cpucol.deployer.yml

status-cpucol:
	$(PYTHON) -m deployer.cli status /home/sanek/projects/claudecode/test_proj --manifest docs/sample-manifests/cpucol.deployer.yml --environment dev

docker-build:
	docker build -t home-paas-deployer:latest .

reset-dev:
	rm -f "$(DEV_STATE_DB)"
	rm -rf "$(DEV_RUNTIME_DIR)"
	@echo "Reset dev deployer state: $(DEV_STATE_DB), $(DEV_RUNTIME_DIR)"

reset-test:
	rm -f "$(TEST_STATE_DB)"
	rm -rf "$(TEST_RUNTIME_DIR)"
	@echo "Reset test deployer state: $(TEST_STATE_DB), $(TEST_RUNTIME_DIR)"

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
