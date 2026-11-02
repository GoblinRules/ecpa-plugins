package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"sync"

	"gopkg.in/yaml.v3"
)

// pluginSettings holds the plugin's own config from
// plugins.configs.zai-provider, delivered via plugin.register/reconfigure.
type pluginSettings struct {
	// Core-owned fields are included in the lifecycle configuration envelope.
	Enabled            *bool  `yaml:"enabled"`
	Priority           int    `yaml:"priority"`
	HistoryTimezone    string `yaml:"history-timezone"`
	APIKeyName         string `yaml:"api-key-name"`
	EnableBrowserLogin bool   `yaml:"enable-browser-login"`
	ExpectedAccount    string `yaml:"expected-account"`
	OrganizationID     string `yaml:"organization-id"`
	ProjectID          string `yaml:"project-id"`
	BillingConfirmed   bool   `yaml:"billing-confirmed"`
}

var settingsMu sync.RWMutex
var settings pluginSettings

// parsePluginConfig rejects unknown fields and incomplete browser-login consent.
// Each reconfiguration invalidates pending browser flows.
func parsePluginConfig(raw []byte) error {
	var next pluginSettings
	if len(raw) > 0 {
		decoder := yaml.NewDecoder(bytes.NewReader(raw))
		decoder.KnownFields(true)
		if errUnmarshal := decoder.Decode(&next); errUnmarshal != nil {
			return fmt.Errorf("invalid plugin configuration: check field names and value types")
		}
	}
	if next.EnableBrowserLogin {
		validID := regexp.MustCompile(`^[A-Za-z0-9_-]{1,128}$`)
		if strings.TrimSpace(next.ExpectedAccount) == "" || !validID.MatchString(next.OrganizationID) || !validID.MatchString(next.ProjectID) || strings.TrimSpace(next.APIKeyName) == "" || !next.BillingConfirmed {
			return fmt.Errorf("browser login requires an expected account, explicit organisation/project IDs, existing key name and billing confirmation")
		}
	}
	settingsMu.Lock()
	settings = next
	settingsMu.Unlock()
	flowsMu.Lock()
	flows = map[string]*loginFlow{}
	flowsMu.Unlock()
	return nil
}

// preferredTimezone returns the configured display timezone, if any.
func preferredTimezone() string {
	settingsMu.RLock()
	defer settingsMu.RUnlock()
	return settings.HistoryTimezone
}

func preferredAPIKeyName() string {
	settingsMu.RLock()
	defer settingsMu.RUnlock()
	if name := strings.TrimSpace(settings.APIKeyName); name != "" {
		return name
	}
	return "zai-provider"
}

// lifecycleConfigYAML extracts config_yaml from a register/reconfigure payload.
func lifecycleConfigYAML(payload []byte) []byte {
	var req struct {
		ConfigYAML []byte `json:"config_yaml"`
	}
	if errUnmarshal := json.Unmarshal(payload, &req); errUnmarshal != nil {
		return nil
	}
	return req.ConfigYAML
}

func settingsSnapshot() pluginSettings {
	settingsMu.RLock()
	defer settingsMu.RUnlock()
	return settings
}
