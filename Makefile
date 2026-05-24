# Vipin Lab

.PHONY: install test lint clean run-discover run-status

install:
	pip install -e ".[dev]"
	cp -n .env.example .env || true
	@echo ""
	@echo "  Add ANTHROPIC_API_KEY to .env"
	@echo "  Then: make run-status"

test:
	pytest tests/ -v --tb=short

lint:
	ruff check lab/ cli/ tests/
	ruff format --check lab/ cli/ tests/

format:
	ruff format lab/ cli/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .ruff_cache .mypy_cache

run-status:
	python -m cli.main status

run-discover:
	@read -p "Domain (e.g. LLM4Rec): " domain; \
	python -m cli.main discover "$$domain"

run-extend:
	@echo "Usage: python -m cli.main extend <domain> --method '...' --limits '...'"

help:
	@echo ""
	@echo "  make install      Install dependencies and copy .env.example"
	@echo "  make test         Run test suite"
	@echo "  make lint         Check code style"
	@echo "  make format       Auto-format code"
	@echo "  make run-status   Check API key configuration"
	@echo "  make run-discover Start a discovery session"
	@echo ""
