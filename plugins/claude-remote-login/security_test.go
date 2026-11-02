package main

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestReviewConfirmationPreservesSettingsAndRejectsConcurrentChanges(t *testing.T) {
	host := &fakeHost{}
	existing := map[string]any{"type": "claude", "prefix": "work", "disabled": true, "claude_device_ids": []string{"existing-device"}}
	var filename string
	s := newService(func(method string, payload any) (json.RawMessage, error) {
		if method == "host.auth.list" {
			return raw(map[string]any{"files": []map[string]string{{"name": filename, "auth_index": "existing"}}}), nil
		}
		if method == "host.auth.get" {
			return raw(map[string]any{"json": existing}), nil
		}
		return host.call(method, payload)
	})
	flow, _ := s.start()
	state := flow["state"].(string)
	// Discover the proposed filename through staged acquisition, not a saved record.
	if _, err := s.complete(state, "code#"+state, ""); err != nil {
		t.Fatal(err)
	}
	filename = s.sessions[state].filename
	if _, err := s.complete(state, "", ""); err != nil {
		t.Fatal(err)
	}
	if host.saves != 0 {
		t.Fatal("saved during review")
	}
	if _, err := s.confirm(state, "wrong@example.test", "org-1", true, ""); err == nil {
		t.Fatal("wrong identity confirmed")
	}
	existing["prefix"] = "changed"
	if _, err := confirmTest(s, state); err == nil || host.saves != 0 {
		t.Fatal("concurrent settings change overwritten")
	}
	if _, err := s.complete(state, "", ""); err != nil {
		t.Fatal(err)
	}
	if _, err := confirmTest(s, state); err != nil {
		t.Fatal(err)
	}
	if host.saved["prefix"] != "changed" || host.saved["disabled"] != true || host.saved["claude_device_ids"].([]any)[0] != "existing-device" {
		t.Fatal("settings were lost", host.saved)
	}
}
func TestAccountReadFailuresNeverSaveAndCanRetryWithoutCodeReplay(t *testing.T) {
	for _, failure := range []string{"list", "get", "malformed"} {
		t.Run(failure, func(t *testing.T) {
			host := &fakeHost{}
			broken := false
			filename := ""
			s := newService(func(method string, payload any) (json.RawMessage, error) {
				if method == "host.auth.list" {
					if broken && failure == "list" {
						return nil, errors.New("secret exception")
					}
					return raw(map[string]any{"files": []map[string]string{{"name": filename, "auth_index": "saved"}}}), nil
				}
				if method == "host.auth.get" {
					if broken && failure == "get" {
						return nil, errors.New("secret exception")
					}
					if broken && failure == "malformed" {
						return raw(map[string]any{"json": nil}), nil
					}
					return raw(map[string]any{"json": map[string]any{"type": "claude"}}), nil
				}
				return host.call(method, payload)
			})
			flow, _ := s.start()
			state := flow["state"].(string)
			s.complete(state, "code#"+state, "")
			filename = s.sessions[state].filename
			s.complete(state, "", "")
			broken = true
			if _, err := confirmTest(s, state); err == nil || strings.Contains(err.Error(), "secret exception") || host.saves != 0 {
				t.Fatal("unsafe failed read", err)
			}
			broken = false
			if _, err := confirmTest(s, state); err != nil {
				t.Fatal(err)
			}
			if host.exchanges != 1 {
				t.Fatal("authorization code replayed")
			}
		})
	}
}
func TestCancelAndExpiryDiscardPendingCredentials(t *testing.T) {
	for _, cancel := range []bool{true, false} {
		s := newService((&fakeHost{}).call)
		flow, _ := s.start()
		state := flow["state"].(string)
		s.complete(state, "code#"+state, "")
		draft := s.sessions[state]
		if cancel {
			s.cancel(state)
		} else {
			s.now = func() time.Time { return draft.expires.Add(time.Second) }
			confirmTest(s, state)
		}
		if draft.credential != nil || draft.verifier != "" || s.sessions[state] != nil {
			t.Fatal("discard retained credentials")
		}
	}
}
