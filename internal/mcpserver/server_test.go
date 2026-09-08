package mcpserver

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"requestme/internal/client"
)

const branch = "01a07bde-f801-7992-bb5d-b80b58adac3f"

func req(meta mcp.Meta) *mcp.CallToolRequest {
	return &mcp.CallToolRequest{Params: &mcp.CallToolParamsRaw{Meta: meta}}
}

func TestRoutingRequiresConcreteThread(t *testing.T) {
	if _, _, err := routing(req(nil)); err == nil {
		t.Fatal("expected missing metadata error")
	}
	got, _, err := routing(req(mcp.Meta{"threadId": branch}))
	if err != nil || got != branch {
		t.Fatalf("routing: %q %v", got, err)
	}
}

func TestRoutingAllowsNestedBranchAndRejectsConflict(t *testing.T) {
	root := "01a07bde-f801-7992-bb5d-b80b58adac3f"
	branchID := "01a07bde-f801-7992-bb5d-b80b58adac30"
	nested := map[string]any{"thread_id": branchID, "session_id": root}
	got, _, err := routing(req(mcp.Meta{"x-codex-turn-metadata": nested}))
	if err != nil || got != branchID {
		t.Fatalf("nested: %q %v", got, err)
	}
	if _, _, err := routing(req(mcp.Meta{"threadId": root, "x-codex-turn-metadata": map[string]any{"thread_id": "01a07bde-f801-7992-bb5d-b80b58adac30"}})); err == nil {
		t.Fatal("expected conflict")
	}
}

func TestMessageIDStable(t *testing.T) {
	a := messageID(branch, "call", "notify")
	if a != messageID(branch, "call", "notify") || len(a) != 64 {
		t.Fatal(a)
	}
}

func TestHandlersRejectInvalidInputBeforeNetwork(t *testing.T) {
	s := New(nil, "test", nil)
	if _, _, err := s.Notify(context.Background(), req(mcp.Meta{"threadId": branch}), notifyInput{}); err == nil {
		t.Fatal("expected markdown error")
	}
}

func TestMCPTransportSchemaAndError(t *testing.T) {
	s := New(client.New("http://127.0.0.1:1", "x"), "test", nil)
	server := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	s.Install(server)
	ct, st := mcp.NewInMemoryTransports()
	ss, err := server.Connect(context.Background(), st, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer ss.Close()
	cs, err := mcp.NewClient(&mcp.Implementation{Name: "client"}, nil).Connect(context.Background(), ct, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer cs.Close()
	tools, err := cs.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	wantNames := map[string]bool{"send_user_notification": false, "request_user_response": false, "close_user_request": false}
	for _, tool := range tools.Tools {
		if _, ok := wantNames[tool.Name]; !ok {
			t.Fatalf("unexpected tool name: %s", tool.Name)
		}
		wantNames[tool.Name] = true
		b, _ := json.Marshal(tool.InputSchema)
		text := string(b)
		if contains(text, "threadId") || contains(text, "thread_id") || contains(text, "callId") {
			t.Fatalf("routing metadata leaked into %s schema: %s", tool.Name, text)
		}
	}
	for name, found := range wantNames {
		if !found {
			t.Fatalf("missing tool: %s", name)
		}
	}
	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "send_user_notification", Arguments: map[string]any{"markdown": "x"}})
	if err != nil {
		t.Fatal(err)
	}
	if !res.IsError {
		t.Fatal("missing metadata should be a tool error")
	}
}

func TestMCPForwardsMarkdownOptionsAndCloseScope(t *testing.T) {
	var mu sync.Mutex
	var messages []map[string]any
	var closeThread string
	h := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/requests" {
			var v map[string]any
			_ = json.NewDecoder(r.Body).Decode(&v)
			mu.Lock()
			messages = append(messages, v)
			mu.Unlock()
			w.Header().Set("Content-Type", "application/json")
			out, _ := json.Marshal(map[string]any{"id": v["id"], "status": "sent"})
			_, _ = w.Write(out)
			return
		}
		if strings.HasPrefix(r.URL.Path, "/v1/requests/") && strings.HasSuffix(r.URL.Path, "/close") {
			var v map[string]string
			_ = json.NewDecoder(r.Body).Decode(&v)
			closeThread = v["thread_id"]
			w.WriteHeader(http.StatusNoContent)
			return
		}
		http.NotFound(w, r)
	}))
	defer h.Close()
	s := New(client.New(h.URL, "x"), "test", nil)
	server := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	s.Install(server)
	ct, st := mcp.NewInMemoryTransports()
	ss, err := server.Connect(context.Background(), st, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer ss.Close()
	cs, err := mcp.NewClient(&mcp.Implementation{Name: "client"}, nil).Connect(context.Background(), ct, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer cs.Close()
	meta := mcp.Meta{"threadId": branch, "callId": "c1"}
	options := []map[string]any{{"id": "a", "label": "A", "value": "alpha"}}
	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "request_user_response", Meta: meta, Arguments: map[string]any{"markdown": "**keep**", "options": options}})
	if err != nil || res.IsError {
		t.Fatalf("request_human: %v %#v", err, res)
	}
	mu.Lock()
	got := messages[0]
	mu.Unlock()
	if got["markdown"] != "**keep**" || got["thread_id"] != branch {
		t.Fatalf("forwarded message: %#v", got)
	}
	if len(got["options"].([]any)) != 1 {
		t.Fatalf("options lost: %#v", got["options"])
	}
	res, err = cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "close_user_request", Meta: mcp.Meta{"threadId": branch}, Arguments: map[string]any{"request_id": "m1"}})
	if err != nil || res.IsError {
		t.Fatalf("close: %v %#v", err, res)
	}
	if closeThread != branch {
		t.Fatalf("close routed to %q", closeThread)
	}
}

func contains(s, part string) bool {
	for i := 0; i+len(part) <= len(s); i++ {
		if s[i:i+len(part)] == part {
			return true
		}
	}
	return false
}
