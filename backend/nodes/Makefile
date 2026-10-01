NODES := http-request agent script aap-job aap-workflow
CONTAINER_ENGINE ?= podman
REGISTRY ?= localhost
TAG ?= migration-test
NODE ?= http-request

.PHONY: install typecheck test node-images node-image push-node-images push-node-image manifests
install:
	uv sync --frozen --all-packages --group dev

typecheck:
	uv run --frozen --all-packages mypy --config-file pyproject.toml _protocol/src _shared/src http-request/src agent/src script/src aap-job/src aap-workflow/src

test:
	uv run --frozen --all-packages pytest

node-images:
	@set -e; for node in $(NODES); do $(MAKE) node-image NODE=$$node; done

node-image:
	@case " $(NODES) " in *" $(NODE) "*) ;; *) echo 'Unknown NODE'; exit 2;; esac
	$(CONTAINER_ENGINE) build -f $(NODE)/Containerfile -t $(REGISTRY)/syntara-node-$(NODE):$(TAG) .

push-node-images:
	@set -e; for node in $(NODES); do $(MAKE) push-node-image NODE=$$node; done

push-node-image:
	@case " $(NODES) " in *" $(NODE) "*) ;; *) echo 'Unknown NODE'; exit 2;; esac
	$(CONTAINER_ENGINE) push $(REGISTRY)/syntara-node-$(NODE):$(TAG)

.PHONY: smoke-images
smoke-images:
	CONTAINER_ENGINE=$(CONTAINER_ENGINE) REGISTRY=$(REGISTRY) TAG=$(TAG) uv run --frozen --all-packages python tools/smoke_images.py

.PHONY: proto
proto:
	uv run --frozen --all-packages python -m grpc_tools.protoc -I_protocol/src --python_out=_protocol/src --grpc_python_out=_protocol/src --mypy_out=_protocol/src --mypy_grpc_out=_protocol/src _protocol/src/syntara_node_protocol/node.proto
