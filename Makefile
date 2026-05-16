# Save-Token Makefile

.PHONY: install test commit push providers

install:
	pip install -e .

test:
	save-token ask "1+1等于几" -p deepseek

providers:
	save-token providers

commit:
	git add -A && git commit -m "$$(date +%Y%m%d-%H%M) auto-update" && git push

update:
	git pull && pip install -e .

clean:
	rm -rf build/ dist/ *.egg-info save_token.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
