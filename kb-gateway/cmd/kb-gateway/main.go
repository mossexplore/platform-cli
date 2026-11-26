package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/mossexplore/platform-cli/kb-gateway/internal/auth"
	"github.com/mossexplore/platform-cli/kb-gateway/internal/server"
	"github.com/mossexplore/platform-cli/kb-gateway/internal/weknora"
)

func setting(k, d string) string {
	if s := os.Getenv(k); s != "" {
		return s
	}
	return d
}
func integer(k string, d, upper int) int {
	n, e := strconv.Atoi(setting(k, strconv.Itoa(d)))
	if e != nil || n < 1 || n > upper {
		log.Fatal("invalid ", k)
	}
	return n
}
func networks(name, fallback string) []netip.Prefix {
	raw := setting(name, fallback)
	if raw == "" {
		return nil
	}
	var nets []netip.Prefix
	for _, entry := range strings.Split(raw, ",") {
		p, err := netip.ParsePrefix(strings.TrimSpace(entry))
		if err != nil {
			log.Fatalf("invalid %s: %v", name, err)
		}
		nets = append(nets, p)
	}
	return nets
}
func main() {
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		fmt.Println(version)
		return
	}
	base, e := url.Parse(os.Getenv("WEKNORA_BASE_URL"))
	if e != nil || base.Hostname() == "" || (base.Scheme != "http" && base.Scheme != "https") || base.User != nil || base.Path != "" || base.RawQuery != "" || base.Fragment != "" {
		log.Fatal("invalid WEKNORA_BASE_URL")
	}
	key := os.Getenv("WEKNORA_API_KEY")
	if key == "" {
		log.Fatal("missing WEKNORA_API_KEY")
	}
	vis, e := weknora.ParseVisibility(os.Getenv("WEKNORA_ALLOWED_KB_IDS"), os.Getenv("WEKNORA_PREVIEW_KB_IDS"), os.Getenv("KB_PREVIEW_USERS"))
	if e != nil {
		log.Fatal(e)
	}
	fileList, e := weknora.ParseFileGrants(os.Getenv("KB_FILE_LIST_GRANTS"))
	if e != nil {
		log.Fatal("invalid KB_FILE_LIST_GRANTS: ", e)
	}
	fileDownload, e := weknora.ParseFileGrants(os.Getenv("KB_FILE_DOWNLOAD_GRANTS"))
	if e != nil {
		log.Fatal("invalid KB_FILE_DOWNLOAD_GRANTS: ", e)
	}
	keys, e := auth.Keys(os.Getenv("KB_TICKET_KEYS"))
	if e != nil {
		log.Fatal(e)
	}
	nets := networks("KB_GATEWAY_ALLOWED_CIDRS", "127.0.0.0/8,::1/128")
	trusted := networks("KB_GATEWAY_TRUSTED_PROXY_CIDRS", "")
	timeout := time.Duration(integer("KB_GATEWAY_TIMEOUT_SECONDS", 10, 60)) * time.Second
	c := &weknora.Client{Base: base.String(), Key: key, Visibility: vis, HTTP: &http.Client{Transport: &http.Transport{}, Timeout: timeout, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}, MaxBytes: int64(integer("KB_GATEWAY_MAX_UPSTREAM_BYTES", 8<<20, 64<<20)), Preview: integer("KB_GATEWAY_MAX_PAGE_CONTENT_BYTES", 65536, 1<<20)}
	c.FileList, c.FileDownload = fileList, fileDownload
	c.MaxFileBytes = int64(integer("KB_GATEWAY_MAX_FILE_BYTES", 64<<20, 512<<20))
	h := server.New(c, keys, nets, setting("KB_GATEWAY_AUDIT_DIR", "/var/log/kb-gateway"), integer("KB_GATEWAY_RATE_LIMIT_RPS", 20, 10000), integer("KB_GATEWAY_RATE_LIMIT_BURST", 40, 10000))
	h.TrustedProxies = trusted
	srv := &http.Server{Addr: setting("KB_GATEWAY_LISTEN_ADDR", ":8087"), Handler: h, ReadHeaderTimeout: 5 * time.Second, WriteTimeout: 2*timeout + 5*time.Second, IdleTimeout: time.Minute}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, os.Interrupt)
	defer stop()
	done := make(chan struct{})
	go func() {
		<-ctx.Done()
		end, cancel := context.WithTimeout(context.Background(), 2*timeout+5*time.Second)
		defer cancel()
		srv.Shutdown(end)
		close(done)
	}()
	if e = srv.ListenAndServe(); !errors.Is(e, http.ErrServerClosed) {
		log.Fatal(e)
	}
	<-done
}
