FROM --platform=$BUILDPLATFORM golang:1.25-alpine AS builder
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
ARG TARGETOS
ARG TARGETARCH
RUN test "$TARGETOS/$TARGETARCH" = linux/amd64 \
    && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/telemetry-gateway ./cmd/gateway

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/telemetry-gateway /telemetry-gateway
EXPOSE 8088
USER nonroot:nonroot
ENTRYPOINT ["/telemetry-gateway"]
