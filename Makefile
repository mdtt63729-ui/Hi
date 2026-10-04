install:
	python -m pip install -r requirements.txt
run:
	python -m app.main
test:
	pytest -q
lint:
	python -m compileall -q app tests
docker:
	docker compose up --build
