# Rebuild the whole case study from the Bank of England download through the tests.
# Run `make all` from any working directory; paths are anchored to this file.

REPO := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
export MPLBACKEND := Agg
export PYTHONPATH := $(REPO)

.PHONY: all download load queries analysis test clean

all: download load queries analysis test
	@echo "make all completed"

download:
	cd $(REPO) && $(PYTHON) -m pipeline.download

load:
	cd $(REPO) && $(PYTHON) -m pipeline.load

queries:
	cd $(REPO) && $(PYTHON) -m pipeline.run_queries

analysis:
	cd $(REPO) && $(PYTHON) -m analysis.run_all

test:
	cd $(REPO) && $(PYTHON) -m pytest -q

clean:
	rm -rf $(REPO)/data/processed $(REPO)/outputs/figures $(REPO)/outputs/tables
	rm -f $(REPO)/data/synthetic/northvale_components_SYNTHETIC_weekly_cash_flows.csv
