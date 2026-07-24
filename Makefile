PYTHON ?= python3
NODE ?= node
BASE_REF ?= origin/main
PY_FILES := $(shell find . -path './.git' -prune -o -name '*.py' -print)
PY_TEST_DIRS := $(shell find . -path './.git' -prune -o -type d -name tests -print | sort)
NODE_FILES := $(shell find . -path './.git' -prune -o -name '*.mjs' -print | sort)
NODE_TEST_FILES := $(shell find . -path './.git' -prune -o -path '*/tests/*.mjs' -print | sort)

.PHONY: install-dev validate metadata secrets beads-history-export beads-history-check python-syntax python-tests node-syntax node-tests diff-check validate-online

validate: beads-history-check metadata python-syntax python-tests node-syntax node-tests diff-check

install-dev:
	$(PYTHON) -m pip install --requirement requirements-dev.txt

metadata:
	$(PYTHON) tools/validate_repo.py

secrets:
	$(PYTHON) tools/validate_repo.py --secrets-only

beads-history-export:
	bd export -o .beads/issues.jsonl
	$(PYTHON) tools/beads_history.py export
	$(PYTHON) tools/beads_history.py verify
	$(PYTHON) tools/validate_repo.py
	$(PYTHON) tools/validate_repo.py --secrets-only

beads-history-check:
	$(PYTHON) tools/beads_history.py verify --base-ref "$(BASE_REF)"

python-syntax:
	@tmp=$$(mktemp -d); PYTHONPYCACHEPREFIX=$$tmp $(PYTHON) -m py_compile $(PY_FILES); status=$$?; rm -rf $$tmp; exit $$status

python-tests:
	@status=0; \
	for dir in $(PY_TEST_DIRS); do \
		if find "$$dir" -name 'test_*.py' -print -quit | grep -q .; then \
			echo "Running Python tests in $$dir"; \
			PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s "$$dir" -p 'test_*.py' || status=$$?; \
		fi; \
	done; \
	exit $$status

node-syntax:
	@for file in $(NODE_FILES); do \
		$(NODE) --check "$$file"; \
	done

node-tests:
	@if [ -n "$(NODE_TEST_FILES)" ]; then \
		$(NODE) --test $(NODE_TEST_FILES); \
	fi

diff-check:
	@if git rev-parse --verify "$(BASE_REF)" >/dev/null 2>&1; then \
		git diff --check "$(BASE_REF)"...HEAD; \
	else \
		echo "warning: base ref $(BASE_REF) is unavailable; checking working tree only"; \
	fi
	git diff --check

validate-online:
	$(PYTHON) tools/check_external_links.py
