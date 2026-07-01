PYTHON ?= python3
NODE ?= node
PY_FILES := $(shell find . -path './.git' -prune -o -name '*.py' -print)

.PHONY: validate metadata python-syntax python-tests node-syntax node-tests diff-check

validate: metadata python-syntax python-tests node-syntax node-tests diff-check

metadata:
	$(PYTHON) tools/validate_repo.py

python-syntax:
	@tmp=$$(mktemp -d); PYTHONPYCACHEPREFIX=$$tmp $(PYTHON) -m py_compile $(PY_FILES); status=$$?; rm -rf $$tmp; exit $$status

python-tests:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s estimate-du-units/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s account-meeting-availability/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s uipath-agentic-expansion-planner/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s uipcodedappdeploy/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s llm-council/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s pubsec-big-rocks-row-research/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s gtm-org-proposal-generator/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s usecasehandoff/tests -p 'test_*.py'

node-syntax:
	$(NODE) --check salesforce-meddpicc-update/scripts/meddpicc.mjs

node-tests:
	$(NODE) --test salesforce-meddpicc-update/tests/*.mjs

diff-check:
	git diff --check
