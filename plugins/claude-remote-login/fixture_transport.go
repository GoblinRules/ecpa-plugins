//go:build integration_fixture

package main

import (
	"io"
	"net/http"
	"strings"
)

type fixtureTransport struct{}

func (fixtureTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	body := `{"error":"unsupported fixture request"}`
	status := 400
	switch req.URL.Path {
	case "/v1/oauth/token":
		body = `{"access_token":"fixture-claude-access","refresh_token":"fixture-claude-refresh","expires_in":3600,"account":{"uuid":"fixture-account","email_address":"fixture@example.test"},"organization":{"uuid":"fixture-org","name":"Fixture organisation"}}`
		status = 200
	case "/api/oauth/profile":
		body = `{"account":{"uuid":"fixture-account","email":"fixture@example.test"},"organization":{"uuid":"fixture-org","name":"Fixture organisation"}}`
		status = 200
	case "/api/coding/paas/v4/models":
		body = `{"data":[{"id":"fixture-glm-model"}]}`
		status = 200
	}
	return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(body)), Request: req}, nil
}
func init() { providerClient.Transport = fixtureTransport{} }
