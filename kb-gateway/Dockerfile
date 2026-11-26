FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /kb-gateway ./cmd/kb-gateway
FROM gcr.io/distroless/static:nonroot
COPY --from=build /kb-gateway /kb-gateway
ENTRYPOINT ["/kb-gateway"]
