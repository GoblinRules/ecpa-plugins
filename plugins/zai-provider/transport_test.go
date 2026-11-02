package main

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
)

type testRoundTripper func(*http.Request) (*http.Response, error)

func (f testRoundTripper) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func TestProviderTransportRejectsRedirectsAndMasksFailures(t *testing.T) {
	previous := providerClient
	t.Cleanup(func() { providerClient = previous; closeProviderStreams() })
	calls := 0
	providerClient = &http.Client{Transport: testRoundTripper(func(req *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 307, Header: http.Header{"Location": {"https://collector.invalid/leak"}}, Body: io.NopCloser(strings.NewReader("private-response")), Request: req}, nil
	}), CheckRedirect: previous.CheckRedirect}
	if _, err := executeProviderRequest(providerRequest{Method: "POST", URL: codingChatCompletionsURL, Body: []byte("private-token")}); err == nil || calls != 1 {
		t.Fatal("redirect followed or accepted", calls, err)
	}
	providerClient.Transport = testRoundTripper(func(*http.Request) (*http.Response, error) {
		return nil, errors.New("private-token in transport error")
	})
	if _, err := executeProviderRequest(providerRequest{Method: "POST", URL: codingChatCompletionsURL}); err == nil || strings.Contains(err.Error(), "private-token") {
		t.Fatal("transport error leaked content")
	}
	for _, address := range []string{"https://evil.example/api/x", "http://api.z.ai/api/x", "https://user@api.z.ai/api/x", "https://api.z.ai:999/api/x"} {
		if _, err := executeProviderRequest(providerRequest{Method: "GET", URL: address}); err == nil {
			t.Fatal("bad destination accepted")
		}
	}
}
func TestPrivateTransportStreamingAndResponseBound(t *testing.T) {
	previous := providerClient
	t.Cleanup(func() { providerClient = previous; closeProviderStreams() })
	providerClient = &http.Client{Transport: testRoundTripper(func(req *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader("data: fixture\n\n")), Request: req}, nil
	}), CheckRedirect: previous.CheckRedirect}
	body, _ := json.Marshal(map[string]any{"request": providerRequest{Method: "GET", URL: codingChatCompletionsURL}})
	value, handled, err := providerHTTP("host.http.do_stream", body)
	if err != nil || !handled {
		t.Fatal(err)
	}
	state, _ := json.Marshal(map[string]any{"stream_id": value.(map[string]any)["stream_id"]})
	chunk, _, err := providerHTTP("host.http.stream_read", state)
	if err != nil || string(chunk.(map[string]any)["payload"].([]byte)) != "data: fixture\n\n" {
		t.Fatal("stream data changed", err)
	}
	providerHTTP("host.http.stream_close", state)
	if len(providerStreams.items) != 0 {
		t.Fatal("stream retained")
	}
	providerClient.Transport = testRoundTripper(func(req *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(strings.Repeat("x", (8<<20)+1))), Request: req}, nil
	})
	if _, _, err := providerHTTP("host.http.do", body); err == nil {
		t.Fatal("oversized response accepted")
	}
}
