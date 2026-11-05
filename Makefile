install:
	uv sync

project:
	uv run project

lint:
	uv run ruff check .

build:
	uv build

publish:
	uv build
	uvx twine check dist/*

package-install:
	uv tool install --force dist/*.whl

.PHONY: install project lint build publish package-install
