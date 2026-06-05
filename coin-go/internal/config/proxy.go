package config

import (
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"sync"
	"time"
)

type ProxyConfig struct {
	mu      sync.RWMutex
	Enabled bool
	Port    int
	Host    string
}

func NewProxyConfig() *ProxyConfig {
	enabled := true
	if v := os.Getenv("PROXY_ENABLED"); v != "" {
		enabled = v == "true"
	}
	port := 7890
	if p := os.Getenv("PROXY_PORT"); p != "" {
		if v, err := strconv.Atoi(p); err == nil {
			port = v
		}
	}
	host := os.Getenv("PROXY_HOST")
	if host == "" {
		host = "127.0.0.1"
	}
	return &ProxyConfig{
		Enabled: enabled,
		Port:    port,
		Host:    host,
	}
}

func (c *ProxyConfig) Status() (enabled bool, port int) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.Enabled, c.Port
}

func (c *ProxyConfig) Update(enabled bool, port int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.Enabled = enabled
	c.Port = port
}

func (c *ProxyConfig) ProxyFunc() func(*http.Request) (*url.URL, error) {
	c.mu.RLock()
	enabled := c.Enabled
	port := c.Port
	host := c.Host
	c.mu.RUnlock()

	if !enabled {
		return nil
	}
	proxyURL, err := url.Parse(fmt.Sprintf("http://%s:%d", host, port))
	if err != nil {
		return nil
	}
	return http.ProxyURL(proxyURL)
}

func NewHTTPClient(proxy *ProxyConfig) *http.Client {
	return &http.Client{
		Timeout: 5 * time.Second,
		Transport: &http.Transport{
			Proxy:               proxy.ProxyFunc(),
			MaxIdleConns:        200,
			MaxIdleConnsPerHost: 100,
			MaxConnsPerHost:     100,
			IdleConnTimeout:     90 * time.Second,
		},
	}
}
