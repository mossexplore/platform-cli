package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/config"
	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/forwarder"
	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/server"
)

const version = "0.1.0"

func main() {
	logger := log.New(os.Stderr, "", 0)
	cfg, err := config.Load(os.Getenv)
	if err != nil {
		logger.Fatal(err)
	}
	service := &http.Server{
		Addr: cfg.Listen, Handler: server.New(cfg, forwarder.New(cfg), logger, version),
		ReadHeaderTimeout: 3 * time.Second, ReadTimeout: 10 * time.Second,
		WriteTimeout: cfg.UpstreamTimeout + 12*time.Second, IdleTimeout: 30 * time.Second,
		MaxHeaderBytes: 16 << 10,
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	served := make(chan error, 1)
	go func() { served <- service.ListenAndServe() }()
	select {
	case err := <-served:
		if !errors.Is(err, http.ErrServerClosed) {
			logger.Fatal(err)
		}
	case <-ctx.Done():
		stop()
		drain, cancel := context.WithTimeout(context.Background(), cfg.UpstreamTimeout+time.Second)
		defer cancel()
		if err := service.Shutdown(drain); err != nil {
			logger.Print("gateway shutdown timed out")
			_ = service.Close()
		}
	}
}
