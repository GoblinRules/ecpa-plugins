package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"
)

type fakeHost struct {
	exchanges int
	saves     int
	failSave  bool
	saved     map[string]any
	body      map[string]any
	gate      chan struct{}
	entered   chan struct{}
}

func raw(value any) json.RawMessage { out, _ := json.Marshal(value); return out }
func (f *fakeHost) call(method string, payload any) (json.RawMessage, error) {
	request := payload.(map[string]any)
	switch method {
	case "host.http.do":
		if request["url"] == tokenURL {
			f.exchanges++
			_ = json.Unmarshal(request["body"].([]byte), &f.body)
			if f.entered != nil {
				close(f.entered)
				<-f.gate
			}
			return raw(upstreamResponse{StatusCode: 200, Body: raw(map[string]any{"access_token": "private-access", "refresh_token": "private-refresh", "expires_in": 3600, "account": map[string]string{"uuid": "account-1", "email_address": "test@example.test"}, "organization": map[string]string{"uuid": "org-1", "name": "Test team"}})}), nil
		}
		return raw(upstreamResponse{StatusCode: 200, Body: raw(map[string]any{"account": map[string]string{"uuid": "account-1", "email": "test@example.test"}, "organization": map[string]string{"uuid": "org-1", "name": "Test team"}})}), nil
	case "host.auth.list":
		return raw(map[string]any{"files": []any{}}), nil
	case "host.auth.save":
		f.saves++
		if f.failSave {
			f.failSave = false
			return nil, errors.New("temporary store failure")
		}
		_ = json.Unmarshal(request["json"].(json.RawMessage), &f.saved)
		return raw(map[string]string{"name": request["name"].(string)}), nil
	default:
		return nil, errors.New("unexpected host call")
	}
}
func TestPKCEAndHostedCallback(t *testing.T) {
	host := &fakeHost{}
	s := newService(host.call)
	flow, err := s.start()
	if err != nil {
		t.Fatal(err)
	}
	u, _ := url.Parse(flow["url"].(string))
	state := flow["state"].(string)
	digest := sha256.Sum256([]byte(s.sessions[state].verifier))
	if u.Host != "claude.com" || u.Query().Get("redirect_uri") != redirectURI || u.Query().Get("code_challenge") != base64.RawURLEncoding.EncodeToString(digest[:]) {
		t.Fatal("incorrect hosted redirect or PKCE challenge")
	}
	if strings.Contains(string(raw(flow)), s.sessions[state].verifier) {
		t.Fatal("PKCE verifier exposed")
	}
	if _, err := s.complete(state, "the-code#"+state, "callback"); err != nil {
		t.Fatal(err)
	}
	if host.body["redirect_uri"] != u.Query().Get("redirect_uri") || host.body["state"] != state || host.body["code"] != "the-code" {
		t.Fatal("token exchange differs from authorization session")
	}
	if host.saves != 0 {
		t.Fatal("saved before confirmation")
	}
	if _, err := confirmTest(s, state); err != nil {
		t.Fatal(err)
	}
	if host.saved["type"] != "claude" || host.saved["refresh_token"] != "private-refresh" || host.saved["account_uuid"] != "account-1" {
		t.Fatal("native Claude credential was not saved")
	}
	if host.saved["expired"] == "" || host.saved["claude_device_ids"] == nil {
		t.Fatal("refresh or device metadata missing")
	}
	if _, err := s.complete(state, "the-code#"+state, "callback"); err != nil {
		t.Fatal(err)
	}
	if host.exchanges != 1 || host.saves != 1 {
		t.Fatal("completed code was replayed")
	}
	if s.sessions[state].verifier != "" || s.sessions[state].credential != nil {
		t.Fatal("completed session retained secret material")
	}
}
func TestWrongStateAndExpiredCodeNeverReachClaude(t *testing.T) {
	host := &fakeHost{}
	s := newService(host.call)
	now := time.Unix(1000, 0)
	s.now = func() time.Time { return now }
	flow, _ := s.start()
	state := flow["state"].(string)
	if _, err := s.complete(state, "code#other-state", ""); err == nil {
		t.Fatal("wrong state accepted")
	}
	now = now.Add(sessionTTL)
	if _, err := s.complete(state, "code#"+state, ""); err == nil {
		t.Fatal("expired code accepted")
	}
	if host.exchanges != 0 {
		t.Fatal("invalid session contacted upstream")
	}
}
func TestSaveRetryDoesNotExchangeCodeTwice(t *testing.T) {
	host := &fakeHost{failSave: true}
	s := newService(host.call)
	flow, _ := s.start()
	state := flow["state"].(string)
	if _, err := s.complete(state, "code#"+state, ""); err != nil {
		t.Fatal(err)
	}
	if _, err := confirmTest(s, state); err == nil {
		t.Fatal("save failure hidden")
	}
	if _, err := confirmTest(s, state); err != nil {
		t.Fatal(err)
	}
	if host.exchanges != 1 || host.saves != 2 {
		t.Fatal("save retry repeated token exchange")
	}
}
func TestConcurrentCompletionIsRejected(t *testing.T) {
	host := &fakeHost{gate: make(chan struct{}), entered: make(chan struct{})}
	s := newService(host.call)
	flow, _ := s.start()
	state := flow["state"].(string)
	var wg sync.WaitGroup
	wg.Add(1)
	go func() { defer wg.Done(); _, _ = s.complete(state, "code#"+state, "") }()
	<-host.entered
	if _, err := s.complete(state, "code#"+state, ""); err == nil {
		t.Fatal("concurrent completion accepted")
	}
	close(host.gate)
	wg.Wait()
	if host.exchanges != 1 {
		t.Fatal("multiple token exchanges occurred")
	}
}
func TestInputAndPublicResource(t *testing.T) {
	for _, input := range []string{"", "code#wrong", "code#state#extra", "https://evil.example/?code=one&state=state", "code with spaces"} {
		if _, err := parseCode(input, "state"); err == nil {
			t.Fatalf("invalid code accepted: %q", input)
		}
	}
	for _, input := range []string{"code#state", "code", "https://platform.claude.com/oauth/code/callback?code=code&state=state"} {
		if code, err := parseCode(input, "state"); err != nil || code != "code" {
			t.Fatalf("valid input rejected: %v", err)
		}
	}
	s := newService((&fakeHost{}).call)
	page := s.handle(managementRequest{Method: "GET", Path: resourceURL})
	if page.StatusCode != 200 || !strings.Contains(string(page.Body), "Claude Remote Login") || strings.Contains(string(page.Body), "private-refresh") {
		t.Fatal("public resource is invalid")
	}
	if page.Headers.Get("Cache-Control") != "no-store" {
		t.Fatal("credential page is cacheable")
	}
	response := s.handle(managementRequest{Method: "POST", Path: apiBase + "/complete", Body: []byte(`{"state":"missing","code":"private-code"}`)})
	if response.StatusCode != 404 || strings.Contains(string(response.Body), "private-code") {
		t.Fatal("invalid callback leaked its code")
	}
}

func confirmTest(s *service, state string) (map[string]any, error) {
	return s.confirm(state, "test@example.test", "org-1", true, "")
}
