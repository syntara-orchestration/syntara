FROM golang:1.24-alpine AS runner-build
WORKDIR /src
COPY runner/go.mod ./
COPY runner/main.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w -X main.runtimeLanguage=bash' -o /script-executor .

# This stage supplies Bash and its shared libraries only. The final image is
# distroless, so it contains neither apt nor another package manager.
FROM debian:bookworm-slim AS bash-runtime

FROM gcr.io/distroless/base-debian12:nonroot
COPY --from=bash-runtime /bin/bash /bin/bash
COPY --from=bash-runtime /lib /lib
COPY --from=bash-runtime /usr/lib /usr/lib
COPY --from=runner-build /script-executor /usr/local/bin/script-executor
USER nonroot:nonroot
ENV PATH=/usr/bin:/bin \
    HOME=/nonexistent \
    TMPDIR=/nonexistent \
    TMP=/nonexistent \
    TEMP=/nonexistent \
    SCRIPT_EXECUTOR_KEEP_ALIVE=false \
    SCRIPT_EXECUTOR_MAX_TIMEOUT_SECONDS=300 \
    SCRIPT_EXECUTOR_MAX_OUTPUT_BYTES=1048576
ENTRYPOINT ["/usr/local/bin/script-executor"]
