test:
	@bash test_grisbi.sh

deploy:
	@echo "Install: ln -s $$(pwd)/grisbi.sh ~/bin/grisbi"
	@echo "(no automated deploy — symlink manually)"
