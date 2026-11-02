package main

import (
	"encoding/json"
	"github.com/router-for-me/CLIProxyAPI/v8/sdk/pluginabi"
	"strings"
	"testing"
)

func assertPrivateHeaders(t *testing.T, headers map[string][]string, _ string) {
	t.Helper()
	for name := range headers {
		n := strings.ToLower(name)
		if strings.Contains(n, "zcode") || strings.HasPrefix(n, "x-os") || strings.HasPrefix(n, "x-client") || n == "x-platform" || n == "x-session-id" {
			t.Fatalf("fingerprint header: %s", name)
		}
	}
}
func TestLoginRejectsUnexpectedAccountBeforeKeyAccess(t *testing.T) {
	resetAuthFlows()
	t.Cleanup(resetAuthFlows)
	fake := authLoginRoutes(t, func() string { return strings.ReplaceAll(authReadyBody(), authTestEmail, "wrong@example.test") })
	flow := authStart(t)
	payload, _ := json.Marshal(map[string]any{"State": flow.State, "host_callback_id": "cb-1"})
	if _, err := callAuthMethod(t, pluginabi.MethodAuthLoginPoll, string(payload)); err == nil || !strings.Contains(err.Error(), "does not match") {
		t.Fatal("wrong account was not rejected", err)
	}
	if fake.countURL(customerInfoURL) != 0 || fake.countURL("https://api.z.ai/api/biz/v1/organization/") != 0 {
		t.Fatal("wrong account reached organisation/key access")
	}
}
func TestLoginRejectsUnexpectedAuthorizeDestination(t *testing.T) {
	for _, destination := range []string{"http://zcode.z.ai/oauth", "https://evil.example/oauth", "https://user@zcode.z.ai/oauth", "https://zcode.z.ai:444/oauth"} {
		t.Run(destination, func(t *testing.T) {
			installAuthFakeHost(t, func(call authHostCall) []byte {
				raw, _ := json.Marshal(map[string]any{"data": map[string]string{"flow_id": "fixture", "authorize_url": destination + "?state=fixture"}})
				return authHostEnvelope(200, string(raw))
			})
			if _, err := callAuthMethod(t, pluginabi.MethodAuthLoginStart, `{"host_callback_id":"cb-1"}`); err == nil || !strings.Contains(err.Error(), "invalid authorize url") {
				t.Fatal("unsafe authorization link accepted")
			}
		})
	}
}
func TestBrowserLoginDisabledByDefault(t *testing.T) {
	_ = parsePluginConfig(nil)
	if _, err := handleAuthLoginStart([]byte(`{}`)); err == nil {
		t.Fatal("browser login must require opt in")
	}
}
func TestCoreConfigurationEnvelope(t *testing.T) {
	defer parsePluginConfig(nil)
	if err := parsePluginConfig([]byte("enabled: true\npriority: 10\n")); err != nil {
		t.Fatal(err)
	}
	if err := parsePluginConfig([]byte("enable-browser-login: true\n")); err == nil {
		t.Fatal("incomplete browser configuration accepted")
	}
	if err := parsePluginConfig([]byte("unexpected-secret: do-not-disclose\n")); err == nil || strings.Contains(err.Error(), "do-not-disclose") {
		t.Fatal("unknown configuration must fail without exposing values")
	}
}
func TestProviderDestinationRestrictions(t *testing.T) {
	for _, u := range []string{"https://evil.example/api/test", "https://api.z.ai.evil.example/api/test", "http://api.z.ai/api/test", "https://user@api.z.ai/api/test", "https://api.z.ai:444/api/test", "https://api.z.ai/api/test#fragment"} {
		if allowedProviderURL(u) || allowedZaiOrigin(u) {
			t.Fatal("unsafe destination", u)
		}
	}
}
func TestErrorBodiesNeverReachLogsOrClients(t *testing.T) {
	for _, body := range []string{`{"msg":"private user content"}`, "unknown-private-token response text"} {
		if strings.Contains(upstreamErrorDetail([]byte(body)), "private") {
			t.Fatal("response body disclosed")
		}
	}
}
func TestStreamRejectsUnboundedEvent(t *testing.T) {
	relay := sseRelay{}
	relay.push("", "", []byte(strings.Repeat("x", maxSSEEventBytes)), false)
	if relay.overflow {
		t.Fatal("valid event limit rejected")
	}
	relay.push("", "", []byte("x"), false)
	if !relay.overflow || len(relay.pending) != 0 {
		t.Fatal("unbounded stream buffer retained")
	}
}
