package main

// Provider traffic uses TLS with explicit destinations, bounded responses and
// no redirects. Host logging never receives request or response bodies here.
// Standard HTTPS_PROXY/HTTP_PROXY environment settings apply; CPA per-account
// proxy settings do not apply to this independent transport.
import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"sync"
	"time"
)

var providerClient = func() *http.Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.ResponseHeaderTimeout = 30 * time.Second
	transport.MaxResponseHeaderBytes = 1 << 20
	return &http.Client{Transport: transport, Timeout: 5 * time.Minute, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
}()

type providerRequest struct {
	Method  string
	URL     string
	Headers http.Header
	Body    []byte
}
type providerStream struct {
	mu   sync.Mutex
	body io.ReadCloser
}

var providerStreams = struct {
	sync.Mutex
	items map[string]*providerStream
}{items: map[string]*providerStream{}}

func permittedProviderURL(value string) bool {
	u, err := url.Parse(value)
	if err != nil || u.Scheme != "https" || u.User != nil || u.Fragment != "" {
		return false
	}
	return (u.Host == "platform.claude.com" && u.Path == "/v1/oauth/token") || (u.Host == "api.anthropic.com" && u.Path == "/api/oauth/profile")
}
func executeProviderRequest(request providerRequest) (*http.Response, error) {
	if !permittedProviderURL(request.URL) {
		return nil, errors.New("provider destination rejected")
	}
	if request.Method != "GET" && request.Method != "POST" {
		return nil, errors.New("provider method rejected")
	}
	if len(request.Body) > 16<<20 {
		return nil, errors.New("provider request too large")
	}
	req, err := http.NewRequest(request.Method, request.URL, bytes.NewReader(request.Body))
	if err != nil {
		return nil, errors.New("invalid provider request")
	}
	req.Header = request.Headers.Clone()
	response, err := providerClient.Do(req)
	if err != nil {
		return nil, errors.New("provider connection failed")
	}
	if response.StatusCode >= 300 && response.StatusCode < 400 {
		response.Body.Close()
		return nil, errors.New("provider redirect rejected")
	}
	return response, nil
}

// providerHTTP implements the HTTP-only bridge; authentication storage and
// stream delivery still belong to the core. Tests inject a fake transport.
func providerHTTP(method string, payload []byte) (any, bool, error) {
	switch method {
	case "host.http.do", "host.http.do_stream":
		var wrapper struct {
			Request *providerRequest `json:"request"`
		}
		if json.Unmarshal(payload, &wrapper) != nil {
			return nil, true, errors.New("invalid provider request")
		}
		var request providerRequest
		if wrapper.Request != nil {
			request = *wrapper.Request
		} else if json.Unmarshal(payload, &request) != nil {
			return nil, true, errors.New("invalid provider request")
		}
		response, err := executeProviderRequest(request)
		if err != nil {
			return nil, true, err
		}
		if method == "host.http.do" {
			defer response.Body.Close()
			body, err := io.ReadAll(io.LimitReader(response.Body, (8<<20)+1))
			if err != nil || len(body) > 8<<20 {
				return nil, true, errors.New("provider response incomplete or too large")
			}
			return struct {
				StatusCode int
				Headers    http.Header
				Body       []byte
			}{response.StatusCode, response.Header, body}, true, nil
		}
		providerStreams.Lock()
		defer providerStreams.Unlock()
		if len(providerStreams.items) >= 128 {
			response.Body.Close()
			return nil, true, errors.New("too many provider streams")
		}
		var id [24]byte
		if _, err := rand.Read(id[:]); err != nil {
			response.Body.Close()
			return nil, true, errors.New("cannot identify provider stream")
		}
		key := hex.EncodeToString(id[:])
		providerStreams.items[key] = &providerStream{body: response.Body}
		return map[string]any{"status_code": response.StatusCode, "headers": response.Header, "stream_id": key}, true, nil
	case "host.http.stream_read", "host.http.stream_close":
		var request struct {
			StreamID string `json:"stream_id"`
		}
		if json.Unmarshal(payload, &request) != nil {
			return nil, true, errors.New("invalid stream request")
		}
		providerStreams.Lock()
		stream := providerStreams.items[request.StreamID]
		if method == "host.http.stream_close" {
			delete(providerStreams.items, request.StreamID)
		}
		providerStreams.Unlock()
		if method == "host.http.stream_close" {
			if stream != nil {
				stream.body.Close()
			}
			return map[string]any{}, true, nil
		}
		if stream == nil {
			return nil, true, errors.New("provider stream closed")
		}
		stream.mu.Lock()
		defer stream.mu.Unlock()
		chunk := make([]byte, 32768)
		count, err := stream.body.Read(chunk)
		if err != nil && err != io.EOF {
			return map[string]any{"error": "provider stream interrupted", "done": true}, true, nil
		}
		return map[string]any{"payload": chunk[:count], "done": err == io.EOF}, true, nil
	}
	return nil, false, nil
}
func closeProviderStreams() {
	providerStreams.Lock()
	defer providerStreams.Unlock()
	for id, stream := range providerStreams.items {
		stream.body.Close()
		delete(providerStreams.items, id)
	}
	providerClient.CloseIdleConnections()
}
