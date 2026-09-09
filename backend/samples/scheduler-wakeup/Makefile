ADAPTER ?= http
RECOVERY ?= on
PROFILE ?= default

.PHONY: scheduler-wakeup-poc-up scheduler-wakeup-poc-down scheduler-wakeup-poc-migrate scheduler-wakeup-poc-test scheduler-wakeup-poc-faults scheduler-wakeup-poc-bench scheduler-wakeup-poc-report

scheduler-wakeup-poc-up:
	@echo "The checked-in reference runs in-process; use scheduler-wakeup-poc-migrate or scheduler-wakeup-poc-test."

scheduler-wakeup-poc-down:
	@echo "No in-process reference services remain after the command exits."

scheduler-wakeup-poc-migrate:
	PYTHONPATH=. uv run python -m scheduler_wakeup_poc local

scheduler-wakeup-poc-test:
	PYTHONPATH=. uv run pytest -v tests -m "not integration" --adapter=$(ADAPTER) --recovery=$(RECOVERY)

scheduler-wakeup-poc-faults:
	PYTHONPATH=. uv run pytest -v tests -m faults --adapter=$(ADAPTER) --recovery=$(RECOVERY)

scheduler-wakeup-poc-bench:
	./run-poc.sh $(ADAPTER)

scheduler-wakeup-poc-report:
	PYTHONPATH=. uv run --project ../.. --no-sync python -m scheduler_wakeup_poc.report
