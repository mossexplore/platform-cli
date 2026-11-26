package server

import (
	"net/netip"
	"sync"
	"time"
)

type bucket struct {
	tokens float64
	last   time.Time
}

type limiter struct {
	mu          sync.Mutex
	rate, burst float64
	buckets     map[netip.Addr]bucket
	nextCleanup time.Time
}

func (l *limiter) allow(addr netip.Addr, now time.Time) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	if !now.Before(l.nextCleanup) {
		for address, item := range l.buckets {
			if now.Sub(item.last) >= max(time.Minute, time.Duration(l.burst/l.rate)*time.Second) {
				delete(l.buckets, address)
			}
		}
		l.nextCleanup = now.Add(time.Minute)
	}
	item, exists := l.buckets[addr]
	if !exists {
		if len(l.buckets) >= 4096 {
			return false
		}
		item = bucket{tokens: l.burst, last: now}
	}
	item.tokens = min(l.burst, item.tokens+max(0, now.Sub(item.last).Seconds())*l.rate)
	item.last = now
	allowed := item.tokens >= 1
	if allowed {
		item.tokens--
	}
	l.buckets[addr] = item
	return allowed
}
