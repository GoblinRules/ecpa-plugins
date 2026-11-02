package main

import (
	"encoding/json"
	"errors"
	"github.com/router-for-me/CLIProxyAPI/v8/sdk/pluginabi"
	"strings"
	"testing"
)

func TestKeySetupRequiresConfirmationAndNeverOverwrites(t *testing.T) {
	prev := hostCaller
	t.Cleanup(func() { hostCaller = prev; clearKeyDrafts() })
	saves := 0
	exists := false
	badRead := false
	hostCaller = func(method string, payload []byte) ([]byte, error) {
		switch method {
		case "host.auth.list":
			if badRead {
				return nil, errors.New("private error")
			}
			files := []map[string]string{}
			if exists {
				files = append(files, map[string]string{"name": "zai-key-work.json"})
			}
			return hostEnvelope(t, map[string]any{"files": files}), nil
		case "host.auth.save":
			saves++
			if !strings.Contains(string(payload), "fixture-key-only") {
				t.Fatal("wrong saved credential")
			}
			return hostEnvelope(t, map[string]any{}), nil
		default:
			t.Fatal("unexpected operation", method)
			return nil, nil
		}
	}
	call := func(action string, body any) managementWireResponse {
		raw, _ := json.Marshal(body)
		v, ok := handleKeySetup(managementWireRequest{Method: "POST", Path: keyAPI + "/" + action, Body: raw})
		if !ok {
			t.Fatal("unhandled")
		}
		return v
	}
	review := call("preview", map[string]any{"id": "work", "name": "Work", "key": "fixture-key-only", "billing": "coding"})
	if review.StatusCode != 200 || saves != 0 || strings.Contains(string(review.Body), "fixture-key-only") {
		t.Fatal("preview leaked or saved key", review.StatusCode)
	}
	var data map[string]any
	json.Unmarshal(review.Body, &data)
	state := data["state"]
	if call("confirm", map[string]any{"state": state}).StatusCode != 400 {
		t.Fatal("implicit confirmation")
	}
	badRead = true
	if call("confirm", map[string]any{"state": state, "confirm": true}).StatusCode != 503 || saves != 0 {
		t.Fatal("read failure saved")
	}
	badRead = false
	exists = true
	if call("confirm", map[string]any{"state": state, "confirm": true}).StatusCode != 409 || saves != 0 {
		t.Fatal("existing key overwritten")
	}
	exists = false
	if call("confirm", map[string]any{"state": state, "confirm": true}).StatusCode != 200 || saves != 1 {
		t.Fatal("confirmed save failed")
	}
	if len(keyDrafts.items) != 0 {
		t.Fatal("saved key retained in draft")
	}
	if call("confirm", map[string]any{"state": state, "confirm": true}).StatusCode != 404 || saves != 1 {
		t.Fatal("replayed save")
	}
}
func TestExplicitOrganisationSelectionAndAccountMismatch(t *testing.T) {
	installAuthFakeHost(t, func(call authHostCall) []byte {
		return authHostEnvelope(200, `{"data":{"organizations":[{"organizationId":"default","isDefault":true,"projects":[{"projectId":"wrong"}]},{"organizationId":"chosen","projects":[{"projectId":"first"},{"projectId":"selected"}]}]}}`)
	})
	org, project, err := fetchSelectedOrg("cb", "biz", pluginSettings{OrganizationID: "chosen", ProjectID: "selected"})
	if err != nil || org != "chosen" || project != "selected" {
		t.Fatal("default chosen", err)
	}
	if _, _, err := fetchSelectedOrg("cb", "biz", pluginSettings{OrganizationID: "chosen", ProjectID: "missing"}); err == nil {
		t.Fatal("missing project accepted")
	}
}
func TestInferenceDoesNotInjectPrompts(t *testing.T) {
	body := []byte(`{"model":"fixture-model","messages":[{"role":"system","content":"fixture system"},{"role":"developer","content":"fixture developer"},{"role":"user","content":"fixture user"}]}`)
	testWithFakeHost(t, func(call hostCall, _ int) (any, error) {
		if call.Method == pluginabi.MethodHostHTTPDo {
			var req hostHTTPRequest
			testDecode(t, call.Payload, &req)
			if string(req.Request.Body) != string(body) {
				t.Fatal("prompt payload modified")
			}
			assertPrivateHeaders(t, req.Request.Headers, "")
			return map[string]any{"StatusCode": 200, "Body": []byte(`{"choices":[]}`)}, nil
		}
		return map[string]any{}, nil
	})
	testCallOK(t, pluginabi.MethodExecutorExecute, testJSON(t, map[string]any{"StorageJSON": []byte(`{"type":"zai","api_key":"fixture-key-only"}`), "Payload": body, "host_callback_id": "cb"}))
}
