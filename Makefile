install:
	uv sync

project:
	uv run project

lint:
	uv run ruff check .

build:
	uv build

package-install:
	uv tool install --force dist/*.whl

.PHONY: install project lint build package-install
