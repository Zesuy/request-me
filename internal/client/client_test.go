package client

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"requestme/internal/protocol"
)

func TestClientWireContract(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Error("missing auth")
		}
		if r.URL.Path != "/v1/requests" {
			t.Error(r.URL.Path)
		}
		var m protocol.Message
		json.NewDecoder(r.Body).Decode(&m)
		if m.Markdown != "## 原文\n```\nraw\n```" || m.Options[0].Value != "继续检查" {
			t.Error(m)
		}
		json.NewEncoder(w).Encode(protocol.Sent{ID: m.ID, Status: "sent", MessageID: "qq-id"})
	}))
	defer s.Close()
	c := New(s.URL, "test-token")
	_, err := c.Send(context.Background(), protocol.Message{ID: "request", Markdown: "## 原文\n```\nraw\n```", Options: []protocol.Option{{ID: "a", Label: "继续", Value: "继续检查"}}}, true)
	if err != nil {
		t.Fatal(err)
	}
}

func TestClientDoesNotFollowRedirectOrFalseSuccess(t *testing.T) {
	for _, status := range []int{200, 302, 503} {
		s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Location", "https://example.invalid/")
			w.WriteHeader(status)
			w.Write([]byte(`{"id":"x","status":"pending"}`))
		}))
		_, err := New(s.URL, "secret").Send(context.Background(), protocol.Message{ID: "x"}, true)
		s.Close()
		if err == nil {
			t.Errorf("accepted non-sent response %d", status)
		}
	}
}
