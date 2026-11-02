package main

import (
	"encoding/json"
	"fmt"
	"net/url"
	"strings"

	"github.com/router-for-me/CLIProxyAPI/v8/sdk/pluginabi"
)

// hostCaller issues one host callback RPC. main.go installs the C ABI
// implementation at plugin init; tests replace it with a fake.
var hostCaller = func(method string, payload []byte) ([]byte, error) {
	return nil, fmt.Errorf("host callback %s is unavailable before plugin init", method)
}

func installHostCaller(fn func(method string, payload []byte) ([]byte, error)) {
	hostCaller = func(method string, payload []byte) ([]byte, error) {
		result, handled, err := providerHTTP(method, payload)
		if handled {
			if err != nil {
				return nil, err
			}
			encoded, err := json.Marshal(result)
			if err != nil {
				return nil, err
			}
			return json.Marshal(pluginabi.Envelope{OK: true, Result: encoded})
		}
		return fn(method, payload)
	}
}

// shutdown runs on plugin unload. The host bridge closes open streams, which
// ends every async stream pump; waiting here makes the unload clean.
func shutdown() {
	closeProviderStreams()
	streamPumps.Wait()
	clearKeyDrafts()
	flowsMu.Lock()
	for id := range flows {
		delete(flows, id)
	}
	flowsMu.Unlock()
}

// callHost performs one host callback and decodes the pluginabi envelope.
func callHost(method string, payload any) (json.RawMessage, error) {
	raw, errMarshal := json.Marshal(payload)
	if errMarshal != nil {
		return nil, fmt.Errorf("marshal host request %s: %w", method, errMarshal)
	}
	respRaw, errCall := hostCaller(method, raw)
	if errCall != nil {
		return nil, fmt.Errorf("host operation failed: %s", method)
	}
	var envelope pluginabi.Envelope
	if errUnmarshal := json.Unmarshal(respRaw, &envelope); errUnmarshal != nil {
		return nil, fmt.Errorf("decode host envelope %s: %w", method, errUnmarshal)
	}
	if !envelope.OK {
		return nil, fmt.Errorf("host operation failed: %s", method)
	}
	return envelope.Result, nil
}

type hostLogRequest struct {
	HostCallbackID string         `json:"host_callback_id,omitempty"`
	Level          string         `json:"level"`
	Message        string         `json:"message"`
	Fields         map[string]any `json:"fields,omitempty"`
}

// hostLog sends an event to CPA's logger. Logging is best-effort and never
// changes the result of the operation being logged.
func hostLog(callbackID, level, message string, fields map[string]any) {
	_, _ = callHost(pluginabi.MethodHostLog, hostLogRequest{
		HostCallbackID: callbackID, Level: level, Message: message, Fields: fields,
	})
}

// hostHTTPRequest is the wire shape of a host.http.do request. The host
// response decodes into pluginapi.HTTPResponse-shaped JSON.
type hostHTTPRequest struct {
	HostCallbackID string              `json:"host_callback_id,omitempty"`
	OperationID    string              `json:"operation_id,omitempty"`
	Request        hostHTTPRequestSpec `json:"request,omitempty"`
}

type hostHTTPRequestSpec struct {
	Method  string              `json:"method,omitempty"`
	URL     string              `json:"url,omitempty"`
	Headers map[string][]string `json:"headers,omitempty"`
	Body    []byte              `json:"body,omitempty"`
}

type hostHTTPResponse struct {
	StatusCode int                 `json:"StatusCode"`
	Headers    map[string][]string `json:"Headers,omitempty"`
	Body       []byte              `json:"Body"`
}

// hostDo performs one upstream HTTP request through the host transport so
// proxy policy and request logging apply. The caller owns Authorization.
func hostDo(callbackID, method, url string, headers map[string][]string, body []byte) (*hostHTTPResponse, error) {
	if !allowedProviderURL(url) {
		return nil, fmt.Errorf("provider destination rejected")
	}
	if callbackID == "" {
		return nil, fmt.Errorf("host callback id is required for upstream requests")
	}
	payload := hostHTTPRequest{HostCallbackID: callbackID, Request: hostHTTPRequestSpec{
		Method: method, URL: url, Headers: headers, Body: body,
	}}
	result, errCall := callHost(pluginabi.MethodHostHTTPDo, payload)
	if errCall != nil {
		return nil, errCall
	}
	var resp hostHTTPResponse
	if errUnmarshal := json.Unmarshal(result, &resp); errUnmarshal != nil {
		return nil, fmt.Errorf("decode host HTTP response: %w", errUnmarshal)
	}
	return &resp, nil
}

// upstreamError converts a non-2xx upstream response into an error that carries
// the upstream status and a sanitized message. Known credentials are redacted
// before a short body prefix is kept; response headers are never copied.
func upstreamError(status int, body []byte, secrets ...string) error {
	detail := upstreamErrorDetail(body, secrets...)
	if detail == "" {
		return fmt.Errorf("upstream returned status %d", status)
	}
	return fmt.Errorf("upstream returned status %d: %s", status, detail)
}

func upstreamErrorDetail(_ []byte, _ ...string) string {
	return "Provider request failed; check the HTTP status, credentials and connectivity."
}
func allowedProviderURL(value string) bool {
	u, err := url.Parse(value)
	return err == nil && u.Scheme == "https" && u.User == nil && u.Fragment == "" && (u.Host == "api.z.ai" || u.Host == "zcode.z.ai") && strings.HasPrefix(u.Path, "/api/")
}

func redactSecrets(detail string, secrets []string) string {
	for _, secret := range secrets {
		if secret = strings.TrimSpace(secret); secret != "" {
			detail = strings.ReplaceAll(detail, secret, "[redacted]")
		}
	}
	return detail
}

func sanitizeDetail(detail string) string {
	detail = strings.TrimSpace(strings.Join(strings.Fields(detail), " "))
	if len(detail) > 300 {
		return detail[:300]
	}
	return detail
}
