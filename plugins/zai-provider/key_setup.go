package main

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"sync"
	"time"
)

const keyAPI = "/v0/management/plugins/zai-provider/key"
const setupURL = "/v0/resource/plugins/zai-provider/setup"

//go:embed setup.html
var setupPage []byte

type keyDraft struct {
	storage zaiStorage
	expires time.Time
	timer   *time.Timer
}

var keyDrafts = struct {
	sync.Mutex
	items map[string]*keyDraft
}{items: map[string]*keyDraft{}}

func handleKeySetup(req managementWireRequest) (managementWireResponse, bool) {
	if req.Path == setupURL && req.Method == "GET" {
		return managementWireResponse{StatusCode: 200, Headers: map[string][]string{"Content-Type": {"text/html; charset=utf-8"}, "Cache-Control": {"no-store"}, "Referrer-Policy": {"no-referrer"}, "X-Content-Type-Options": {"nosniff"}, "Content-Security-Policy": {"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'self' http://tauri.localhost https://tauri.localhost tauri://localhost"}}, Body: setupPage}, true
	}
	if !strings.HasPrefix(req.Path, keyAPI+"/") {
		return managementWireResponse{}, false
	}
	if req.Method != "POST" {
		return managementError(405, "Use POST"), true
	}
	if len(req.Body) > 8192 {
		return managementError(413, "Request too large"), true
	}
	var body struct {
		ID      string `json:"id"`
		Name    string `json:"name"`
		Key     string `json:"key"`
		Billing string `json:"billing"`
		State   string `json:"state"`
		Confirm bool   `json:"confirm"`
	}
	if json.Unmarshal(req.Body, &body) != nil {
		return managementError(400, "Invalid request"), true
	}
	keyDrafts.Lock()
	defer keyDrafts.Unlock()
	if req.Path == keyAPI+"/preview" {
		if len(keyDrafts.items) >= 64 {
			return managementError(429, "Too many pending connections; finish or cancel one"), true
		}
		body.Name = strings.TrimSpace(body.Name)
		body.Key = strings.TrimSpace(body.Key)
		if !regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,63}$`).MatchString(body.ID) || body.Name == "" || len(body.Name) > 100 || len(body.Key) < 8 || len(body.Key) > 4096 || strings.ContainsAny(body.Key, " \r\n\t") || body.Billing != "coding" {
			return managementError(400, "Supply a stable ID, name and an existing Coding Plan key. Check its billing type in the Z.ai dashboard."), true
		}
		state, err := randomHex(32)
		if err != nil {
			return managementError(500, "Cannot create review session"), true
		}
		storage := zaiStorage{Version: storageVersion, Type: providerID, APIKey: body.Key, UserID: "key-" + body.ID, Label: body.Name, BillingMode: body.Billing, ObtainedAt: nowRFC3339()}
		draft := &keyDraft{storage: storage, expires: time.Now().Add(10 * time.Minute)}
		draft.timer = time.AfterFunc(10*time.Minute, func() {
			keyDrafts.Lock()
			defer keyDrafts.Unlock()
			if d := keyDrafts.items[state]; d != nil {
				d.storage.APIKey = ""
				delete(keyDrafts.items, state)
			}
		})
		keyDrafts.items[state] = draft
		return managementJSON(200, map[string]any{"state": state, "name": body.Name, "id": body.ID, "billing": "Coding Plan (declared by you; not independently verified)", "message": "Key held temporarily for review; not saved or sent to Z.ai."}), true
	}
	draft := keyDrafts.items[body.State]
	if draft == nil || time.Now().After(draft.expires) {
		return managementError(404, "Review expired; start again"), true
	}
	if req.Path == keyAPI+"/cancel" {
		draft.timer.Stop()
		draft.storage.APIKey = ""
		delete(keyDrafts.items, body.State)
		return managementJSON(200, map[string]bool{"cancelled": true}), true
	}
	if req.Path != keyAPI+"/confirm" {
		return managementError(404, "Unknown action"), true
	}
	if !body.Confirm {
		return managementError(400, "Explicit confirmation is required"), true
	}
	name := draft.storage.authID() + ".json"
	raw, err := callHost("host.auth.list", map[string]any{})
	var list struct {
		Files *[]struct {
			Name string `json:"name"`
		} `json:"files"`
	}
	if err != nil || json.Unmarshal(raw, &list) != nil || list.Files == nil {
		return managementError(503, "Cannot check existing credentials; nothing was saved"), true
	}
	for _, file := range *list.Files {
		if file.Name == name {
			return managementError(409, "This ID already exists. Choose another ID; existing accounts are never overwritten here."), true
		}
	}
	record, _ := json.Marshal(draft.storage)
	if _, err = callHost("host.auth.save", map[string]any{"name": name, "json": json.RawMessage(record)}); err != nil {
		return managementError(503, "Saving failed. Retry confirmation."), true
	}
	draft.timer.Stop()
	draft.storage.APIKey = ""
	delete(keyDrafts.items, body.State)
	return managementJSON(200, map[string]string{"status": "saved", "message": fmt.Sprintf("Saved %s. Model availability and billing still depend on the key and provider.", draft.storage.Label)}), true
}

func clearKeyDrafts() {
	keyDrafts.Lock()
	defer keyDrafts.Unlock()
	for state, d := range keyDrafts.items {
		d.timer.Stop()
		d.storage.APIKey = ""
		delete(keyDrafts.items, state)
	}
}
