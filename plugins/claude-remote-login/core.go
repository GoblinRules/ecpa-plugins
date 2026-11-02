package main

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

const (
	pluginID      = "claude-remote-login"
	pluginVersion = "1.1.0"
	apiBase       = "/v0/management/plugins/" + pluginID
	resourceURL   = "/v0/resource/plugins/" + pluginID + "/login"
	authorizeURL  = "https://claude.com/cai/oauth/authorize"
	redirectURI   = "https://platform.claude.com/oauth/code/callback"
	tokenURL      = "https://platform.claude.com/v1/oauth/token"
	profileURL    = "https://api.anthropic.com/api/oauth/profile"
	clientID      = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
	scope         = "user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload"
	sessionTTL    = 15 * time.Minute
)

type hostCaller func(string, any) (json.RawMessage, error)
type managementRequest struct {
	Method         string
	Path           string
	Body           []byte
	HostCallbackID string `json:"host_callback_id"`
}
type managementResponse struct {
	StatusCode int
	Headers    http.Header
	Body       []byte
}
type apiError struct {
	status  int
	message string
}

func (e *apiError) Error() string           { return e.message }
func fail(status int, message string) error { return &apiError{status, message} }

type loginSession struct {
	state      string
	verifier   string
	expires    time.Time
	busy       bool
	completed  bool
	credential map[string]any
	filename   string
	email      string
	baseline   string
	reviewed   bool
	timer      *time.Timer
}
type service struct {
	mu       sync.Mutex
	saveMu   sync.Mutex
	sessions map[string]*loginSession
	call     hostCaller
	now      func() time.Time
}

func newService(call hostCaller) *service {
	return &service{sessions: make(map[string]*loginSession), call: call, now: time.Now}
}
func main() {}

func randomValue() (string, error) {
	var value [32]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(value[:]), nil
}
func (s *service) start() (map[string]any, error) {
	state, err := randomValue()
	if err != nil {
		return nil, fail(500, "Unable to generate a login session.")
	}
	verifier, err := randomValue()
	if err != nil {
		return nil, fail(500, "Unable to generate PKCE material.")
	}
	digest := sha256.Sum256([]byte(verifier))
	query := url.Values{
		"client_id": {clientID}, "response_type": {"code"}, "code": {"true"},
		"redirect_uri": {redirectURI}, "scope": {scope}, "state": {state},
		"code_challenge_method": {"S256"}, "code_challenge": {base64.RawURLEncoding.EncodeToString(digest[:])},
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	now := s.now()
	for key, session := range s.sessions {
		if !session.busy && !now.Before(session.expires) {
			s.forgetLocked(key)
		}
	}
	if len(s.sessions) >= 128 {
		return nil, fail(429, "Too many pending logins. Finish or cancel an existing login first.")
	}
	expires := now.Add(sessionTTL)
	session := &loginSession{state: state, verifier: verifier, expires: expires}
	s.sessions[state] = session
	session.timer = time.AfterFunc(sessionTTL, func() { s.expire(state) })
	return map[string]any{"state": state, "url": authorizeURL + "?" + query.Encode(), "expires_at": expires.UTC().Format(time.RFC3339)}, nil
}

func parseCode(input, expectedState string) (string, error) {
	input = strings.TrimSpace(input)
	if input == "" || len(input) > 4096 || strings.ContainsAny(input, " \t\r\n") {
		return "", fail(400, "Paste the complete authorization code from this login link.")
	}
	state := ""
	code := input
	if strings.Contains(input, "://") {
		u, err := url.Parse(input)
		if err != nil || u.Scheme != "https" || u.Host != "platform.claude.com" || u.Path != "/oauth/code/callback" || u.User != nil {
			return "", fail(400, "Unexpected callback URL. Paste the displayed code instead.")
		}
		code = u.Query().Get("code")
		state = u.Query().Get("state")
	}
	if strings.Contains(code, "#") {
		parts := strings.Split(code, "#")
		if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
			return "", fail(400, "Invalid authorization code format.")
		}
		if state != "" && state != parts[1] {
			return "", fail(400, "Conflicting authorization states.")
		}
		code, state = parts[0], parts[1]
	}
	if code == "" || (state != "" && state != expectedState) {
		return "", fail(400, "This code belongs to a different login attempt. Use its original link.")
	}
	return code, nil
}

type upstreamResponse struct {
	StatusCode int
	Headers    http.Header
	Body       []byte
}

func (s *service) http(callbackID, method, endpoint, token string, body any) (upstreamResponse, error) {
	var data []byte
	if body != nil {
		var err error
		data, err = json.Marshal(body)
		if err != nil {
			return upstreamResponse{}, err
		}
	}
	headers := http.Header{"Accept": {"application/json"}}
	if body != nil {
		headers.Set("Content-Type", "application/json")
	}
	if token != "" {
		headers.Set("Authorization", "Bearer "+token)
	}
	raw, err := s.call("host.http.do", map[string]any{"host_callback_id": callbackID, "method": method, "url": endpoint, "headers": headers, "body": data})
	if err != nil {
		return upstreamResponse{}, fail(502, "Could not reach Claude. Start a new login attempt and retry.")
	}
	var response upstreamResponse
	if json.Unmarshal(raw, &response) != nil {
		return response, fail(502, "Invalid response from the proxy HTTP bridge.")
	}
	return response, nil
}

type tokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int64  `json:"expires_in"`
	Account      struct {
		UUID  string `json:"uuid"`
		Email string `json:"email_address"`
	} `json:"account"`
	Organization struct {
		UUID string `json:"uuid"`
		Name string `json:"name"`
	} `json:"organization"`
}

func (s *service) acquire(session *loginSession, code, callbackID string) error {
	request := struct {
		GrantType    string `json:"grant_type"`
		Code         string `json:"code"`
		RedirectURI  string `json:"redirect_uri"`
		ClientID     string `json:"client_id"`
		CodeVerifier string `json:"code_verifier"`
		State        string `json:"state"`
	}{"authorization_code", code, redirectURI, clientID, session.verifier, session.state}
	response, err := s.http(callbackID, http.MethodPost, tokenURL, "", request)
	if err != nil {
		return err
	}
	if response.StatusCode != 200 {
		return fail(502, fmt.Sprintf("Claude rejected the authorization code (HTTP %d). Generate a fresh link and retry.", response.StatusCode))
	}
	var tokens tokenResponse
	if json.Unmarshal(response.Body, &tokens) != nil || tokens.AccessToken == "" || tokens.RefreshToken == "" || tokens.ExpiresIn <= 0 || tokens.ExpiresIn > 365*24*60*60 {
		return fail(502, "Claude returned an incomplete token response. No credential was saved.")
	}
	profile, errProfile := s.http(callbackID, http.MethodGet, profileURL, tokens.AccessToken, nil)
	if errProfile == nil && profile.StatusCode == 200 {
		var identity struct {
			Account struct {
				UUID  string `json:"uuid"`
				Email string `json:"email"`
			} `json:"account"`
			Organization struct {
				UUID string `json:"uuid"`
				Name string `json:"name"`
			} `json:"organization"`
		}
		if json.Unmarshal(profile.Body, &identity) == nil {
			if identity.Account.UUID != "" {
				tokens.Account.UUID = identity.Account.UUID
			}
			if identity.Account.Email != "" {
				tokens.Account.Email = identity.Account.Email
			}
			if identity.Organization.UUID != "" {
				tokens.Organization.UUID = identity.Organization.UUID
			}
			if identity.Organization.Name != "" {
				tokens.Organization.Name = identity.Organization.Name
			}
		}
	}
	if tokens.Account.Email == "" || (tokens.Account.UUID == "" && tokens.Organization.UUID == "") {
		return fail(502, "Claude did not return an account identity. No credential was saved.")
	}
	identity := tokens.Organization.UUID
	if identity == "" {
		identity = tokens.Account.UUID
	}
	digest := sha256.Sum256([]byte(identity))
	emailForFile := strings.Map(func(r rune) rune {
		if r > 127 || strings.ContainsRune(`/\:*?"<>|`, r) || r < 32 {
			return '_'
		}
		return r
	}, tokens.Account.Email)
	filename := "claude-" + hex.EncodeToString(digest[:])[:8] + "-" + emailForFile + ".json"
	credential := make(map[string]any)
	var device [32]byte
	if _, err := rand.Read(device[:]); err != nil {
		return fail(500, "Could not create the credential identity.")
	}
	if credential == nil {
		credential = make(map[string]any)
	}
	if _, ok := credential["claude_device_ids"]; !ok {
		credential["claude_device_ids"] = []string{hex.EncodeToString(device[:])}
	}
	now := s.now().UTC()
	for key, value := range map[string]any{"type": "claude", "access_token": tokens.AccessToken, "refresh_token": tokens.RefreshToken, "id_token": "", "email": tokens.Account.Email, "account_uuid": tokens.Account.UUID, "organization_uuid": tokens.Organization.UUID, "organization_name": tokens.Organization.Name, "last_refresh": now.Format(time.RFC3339), "expired": now.Add(time.Duration(tokens.ExpiresIn) * time.Second).Format(time.RFC3339)} {
		credential[key] = value
	}
	session.credential = credential
	session.filename = filename
	session.email = tokens.Account.Email
	session.verifier = ""
	return nil
}

func (s *service) complete(state, input, callbackID string) (map[string]any, error) {
	s.mu.Lock()
	session, ok := s.sessions[state]
	if !ok || !s.now().Before(session.expires) {
		if ok && !session.busy {
			s.forgetLocked(state)
		}
		s.mu.Unlock()
		return nil, fail(404, "This login expired or does not exist. Generate a fresh link.")
	}
	if session.completed {
		email := session.email
		s.mu.Unlock()
		return map[string]any{"status": "connected", "email": email}, nil
	}
	if session.busy {
		s.mu.Unlock()
		return nil, fail(409, "This login is already being processed.")
	}
	code, errCode := parseCode(input, state)
	if session.credential == nil && errCode != nil {
		s.mu.Unlock()
		return nil, errCode
	}
	session.busy = true
	s.mu.Unlock()
	defer func() { s.mu.Lock(); session.busy = false; s.mu.Unlock() }()
	if session.credential == nil {
		if err := s.acquire(session, code, callbackID); err != nil {
			s.mu.Lock()
			s.forgetLocked(state)
			s.mu.Unlock()
			return nil, err
		}
	}
	// A read failure must not become permission to overwrite an account.
	existing, baseline, errRead := s.readExisting(session.filename)
	if errRead != nil {
		return nil, errRead
	}
	session.baseline = baseline
	session.reviewed = true
	return map[string]any{"status": "review", "email": session.email, "organization": session.credential["organization_name"], "organization_id": session.credential["organization_uuid"], "replaces_existing": existing != nil}, nil
}

func (s *service) readExisting(filename string) (map[string]any, string, error) {
	data, err := s.call("host.auth.list", map[string]any{})
	if err != nil {
		return nil, "", fail(503, "Cannot read existing accounts. Nothing was saved. Retry account review.")
	}
	var list struct {
		Files *[]struct {
			Name      string `json:"name"`
			AuthIndex string `json:"auth_index"`
		} `json:"files"`
	}
	if json.Unmarshal(data, &list) != nil || list.Files == nil {
		return nil, "", fail(503, "Invalid account listing. Nothing was saved.")
	}
	found := ""
	for _, item := range *list.Files {
		if item.Name == filename {
			if found != "" || item.AuthIndex == "" {
				return nil, "", fail(409, "Ambiguous account listing. Nothing was saved.")
			}
			found = item.AuthIndex
		}
	}
	if found == "" {
		return nil, "absent", nil
	}
	data, err = s.call("host.auth.get", map[string]any{"auth_index": found})
	if err != nil {
		return nil, "", fail(503, "Cannot read existing account settings. Nothing was saved. Retry account review.")
	}
	var record struct {
		JSON json.RawMessage `json:"json"`
	}
	var existing map[string]any
	if json.Unmarshal(data, &record) != nil || json.Unmarshal(record.JSON, &existing) != nil || existing == nil || existing["type"] != "claude" {
		return nil, "", fail(503, "Invalid existing Claude credential. Nothing was saved.")
	}
	digest := sha256.Sum256(record.JSON)
	return existing, hex.EncodeToString(digest[:]), nil
}

func (s *service) confirm(state, email, organization string, consent bool, callbackID string) (map[string]any, error) {
	s.mu.Lock()
	session, ok := s.sessions[state]
	if !ok || !s.now().Before(session.expires) {
		if ok && !session.busy {
			s.forgetLocked(state)
		}
		s.mu.Unlock()
		return nil, fail(404, "Login expired. Start again.")
	}
	if session.busy {
		s.mu.Unlock()
		return nil, fail(409, "Login is being processed.")
	}
	if session.completed {
		s.mu.Unlock()
		return map[string]any{"status": "connected", "email": session.email}, nil
	}
	if !consent || !session.reviewed || session.credential == nil || email != session.email || organization != session.credential["organization_uuid"] {
		s.mu.Unlock()
		return nil, fail(400, "Review and explicitly confirm this account and organization first.")
	}
	session.busy = true
	s.mu.Unlock()
	defer func() { s.mu.Lock(); session.busy = false; s.mu.Unlock() }()
	s.saveMu.Lock()
	defer s.saveMu.Unlock()
	existing, baseline, err := s.readExisting(session.filename)
	if err != nil {
		return nil, err
	}
	if baseline != session.baseline {
		session.reviewed = false
		return nil, fail(409, "Account settings changed since review. Review the account again before confirming.")
	}
	if existing != nil {
		for _, field := range []string{"account_uuid", "organization_uuid"} {
			if previous, ok := existing[field].(string); ok && previous != "" && previous != session.credential[field] {
				return nil, fail(409, "Existing credential identity differs; refusing to replace it.")
			}
		}
	}
	if existing == nil {
		existing = make(map[string]any)
	}
	for key, value := range session.credential {
		if key == "claude_device_ids" && existing[key] != nil {
			continue
		}
		existing[key] = value
	}
	raw, err := json.Marshal(existing)
	if err != nil {
		return nil, fail(500, "Cannot encode account. Nothing was saved.")
	}
	if _, err = s.call("host.auth.save", map[string]any{"name": session.filename, "json": json.RawMessage(raw)}); err != nil {
		return nil, fail(503, "Saving failed. Retry confirmation; the authorization code will not be exchanged again.")
	}
	s.mu.Lock()
	session.completed = true
	session.credential = nil
	session.baseline = ""
	session.expires = s.now().Add(time.Minute)
	if session.timer != nil {
		session.timer.Stop()
	}
	session.timer = time.AfterFunc(time.Minute, func() { s.expire(state) })
	s.mu.Unlock()
	return map[string]any{"status": "connected", "email": session.email}, nil
}

func (s *service) forgetLocked(state string) {
	if session := s.sessions[state]; session != nil {
		if session.timer != nil {
			session.timer.Stop()
		}
		session.verifier = ""
		session.credential = nil
		session.baseline = ""
		delete(s.sessions, state)
	}
}
func (s *service) expire(state string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if session := s.sessions[state]; session != nil {
		if session.busy {
			session.timer = time.AfterFunc(time.Second, func() { s.expire(state) })
			return
		}
		s.forgetLocked(state)
	}
}

func (s *service) cancel(state string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if session, ok := s.sessions[state]; ok && session.busy {
		return fail(409, "The login is being processed. Wait for it to finish.")
	}
	s.forgetLocked(state)
	return nil
}
func jsonResponse(status int, value any) managementResponse {
	body, _ := json.Marshal(value)
	return managementResponse{StatusCode: status, Headers: http.Header{"Content-Type": {"application/json"}, "Cache-Control": {"no-store"}, "X-Content-Type-Options": {"nosniff"}}, Body: body}
}
func (s *service) handle(req managementRequest) managementResponse {
	if req.Method == http.MethodGet && req.Path == resourceURL {
		return managementResponse{StatusCode: 200, Headers: http.Header{"Content-Type": {"text/html; charset=utf-8"}, "Cache-Control": {"no-store"}, "Referrer-Policy": {"no-referrer"}, "X-Content-Type-Options": {"nosniff"}, "Content-Security-Policy": {"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'self' http://tauri.localhost https://tauri.localhost tauri://localhost"}}, Body: loginPage}
	}
	if req.Method != http.MethodPost {
		return jsonResponse(405, map[string]string{"error": "Use POST for login actions."})
	}
	if len(req.Body) > 8192 {
		return jsonResponse(413, map[string]string{"error": "Request body is too large."})
	}
	var body struct {
		State        string `json:"state"`
		Code         string `json:"code"`
		Email        string `json:"email"`
		Organization string `json:"organization_id"`
		Confirm      bool   `json:"confirm"`
	}
	if len(req.Body) > 0 && json.Unmarshal(req.Body, &body) != nil {
		return jsonResponse(400, map[string]string{"error": "Invalid JSON request."})
	}
	var result map[string]any
	var err error
	switch req.Path {
	case apiBase + "/start":
		result, err = s.start()
	case apiBase + "/complete":
		result, err = s.complete(body.State, body.Code, req.HostCallbackID)
	case apiBase + "/confirm":
		result, err = s.confirm(body.State, body.Email, body.Organization, body.Confirm, req.HostCallbackID)
	case apiBase + "/cancel":
		err = s.cancel(body.State)
		result = map[string]any{"status": "cancelled"}
	default:
		return jsonResponse(404, map[string]string{"error": "Unknown plugin endpoint."})
	}
	if err != nil {
		var apiErr *apiError
		if errors.As(err, &apiErr) {
			return jsonResponse(apiErr.status, map[string]string{"error": apiErr.message})
		}
		return jsonResponse(500, map[string]string{"error": "Login could not be completed."})
	}
	return jsonResponse(200, result)
}
