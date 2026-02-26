IMAGE := grisbi-test

.PHONY: test lint deploy

test:
	docker build -t $(IMAGE) .
	docker run --rm -v "$$(pwd)":/app $(IMAGE) sh -c "python3 test_grisbi.py && ruff check . && ruff format --check ."

lint:
	docker build -t $(IMAGE) .
	docker run --rm -v "$$(pwd)":/app $(IMAGE) sh -c "ruff check . && ruff format --check ."

deploy:
	@echo "Install: ln -s $$(pwd)/grisbi.py ~/bin/grisbi"
	@echo "(no automated deploy — symlink manually)"
