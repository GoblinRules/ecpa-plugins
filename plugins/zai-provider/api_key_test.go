package main

import (
	"net/http"
	"strings"
	"testing"
)

func TestExistingKeyNeverCreatesOrSelectsAnother(t *testing.T) {
	for _, data := range []string{`[]`, `[{"name":"other","apiKey":"x","secretKey":"secret"}]`, `[{"name":"chosen","apiKey":"a","secretKey":"x"},{"name":"chosen","apiKey":"b","secretKey":"y"}]`} {
		t.Run(data, func(t *testing.T) {
			fake := installAuthFakeHost(t, func(call authHostCall) []byte {
				if call.Method != http.MethodGet {
					t.Fatal("key mutation attempted")
				}
				return authHostEnvelope(200, `{"code":200,"data":`+data+`}`)
			})
			if _, err := existingAPIKey("cb", "biz", "org", "project", "chosen"); err == nil {
				t.Fatal("ambiguous or absent selection accepted")
			}
			if len(fake.recorded()) != 1 {
				t.Fatal("unexpected key operations")
			}
		})
	}
}
func TestExistingKeyExactSelectionAndMaskedCopy(t *testing.T) {
	fake := installAuthFakeHost(t, func(call authHostCall) []byte {
		if call.Method != http.MethodGet {
			t.Fatal("key mutation")
		}
		if strings.HasSuffix(call.URL, "/copy/id") {
			return authHostEnvelope(200, `{"data":{"secretKey":"fixture-secret"}}`)
		}
		return authHostEnvelope(200, `{"data":[{"name":"chosen","apiKey":"id","secretKey":"****"},{"name":"other","apiKey":"other","secretKey":"wrong"}]}`)
	})
	key, err := existingAPIKey("cb", "biz", "org", "project", "chosen")
	if err != nil || key != "id.fixture-secret" || len(fake.recorded()) != 2 {
		t.Fatal("selected key copy failed", err)
	}
}
