PY ?= python3

.PHONY: install test lint scan collect freeze reproduce paper

install:        ## install the package and CLI
	$(PY) -m pip install .

test:           ## offline unit tests
	$(PY) -m unittest discover -s tests -t . -v

lint:
	$(PY) -m pyflakes compute_forensics tests reproduce.py

scan:           ## fail if an API key is present anywhere outside .env
	$(PY) -m compute_forensics scan-secrets

collect:        ## pull fresh data from GoldRush (needs GOLDRUSH_API_KEY in .env)
	$(PY) -m compute_forensics collect --stage all

freeze:         ## write data/frozen + SHA-256 manifest from data/raw
	$(PY) -m compute_forensics freeze

reproduce:      ## numbers, tables and figures from data/frozen (no key needed)
	$(PY) reproduce.py

paper: reproduce ## build paper/main.pdf
	$(PY) reproduce.py --compile
