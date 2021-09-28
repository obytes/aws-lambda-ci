prepare:
    python3 -m pip install --upgrade pip
    python3 -m pip install --upgrade build
    python3 -m pip install --upgrade twine

publish:
    python3 -m build
	python3 -m twine upload --repository aws-lambda-ci dist/*
