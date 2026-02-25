.PHONY: test lint deploy

test:
	@python3 test_grisbi.py
	ruff check .
	ruff format --check .

lint:
	ruff check .
	ruff format --check .

deploy:
	@echo "Install: ln -s $$(pwd)/grisbi.py ~/bin/grisbi"
	@echo "(no automated deploy — symlink manually)"
