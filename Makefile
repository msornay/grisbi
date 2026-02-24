test:
	@python3 test_grisbi.py

deploy:
	@echo "Install: ln -s $$(pwd)/grisbi.py ~/bin/grisbi"
	@echo "(no automated deploy — symlink manually)"
