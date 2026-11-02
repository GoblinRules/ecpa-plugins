//go:build integration_fixture

package main

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
)

type fixtureTransport struct{}

func (fixtureTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	body := `{"error":"unsupported fixture request"}`
	status := 400
	contentType := "application/json"
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
	case "/api/coding/paas/v4/chat/completions":
		var request struct {
			Stream bool `json:"stream"`
		}
		if json.NewDecoder(req.Body).Decode(&request) == nil {
			status = 200
			body = `{"id":"fixture","object":"chat.completion","model":"fixture-glm-model","choices":[{"index":0,"message":{"role":"assistant","content":"fixture reply"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}`
			if request.Stream {
				contentType = "text/event-stream"
				body = "data: {\"id\":\"fixture\",\"object\":\"chat.completion.chunk\",\"model\":\"fixture-glm-model\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"fixture reply\"},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n"
			}
		}
	}
	return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": {contentType}}, Body: io.NopCloser(strings.NewReader(body)), Request: req}, nil
}
func init() { providerClient.Transport = fixtureTransport{} }
