package codex

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gorilla/websocket"
)

func TestReadOnlySource(t *testing.T) {
	methods := make(chan []string, 1)
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := (&websocket.Upgrader{}).Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()
		var seen []string
		for range 3 {
			var m struct {
				ID     int            `json:"id"`
				Method string         `json:"method"`
				Params map[string]any `json:"params"`
			}
			if conn.ReadJSON(&m) != nil {
				return
			}
			seen = append(seen, m.Method)
			if m.Method == "initialized" {
				continue
			}
			result := map[string]any{}
			if m.Method == "thread/read" {
				if m.Params["includeTurns"] != false || m.Params["threadId"] != testThread {
					t.Error("incorrect thread/read params")
				}
				result["thread"] = map[string]any{"id": testThread, "name": "检查连接", "cwd": "/work/tmp"}
			}
			conn.WriteJSON(map[string]any{"id": m.ID, "result": result})
		}
		methods <- seen
	}))
	defer s.Close()
	r := NewReader(strings.Replace(s.URL, "http", "ws", 1), "")
	source, err := r.Source(context.Background(), testThread)
	if err != nil || source.Title != "检查连接" || source.CWD != "/work/tmp" {
		t.Fatalf("%+v %v", source, err)
	}
	b, _ := json.Marshal(<-methods)
	if string(b) != `["initialize","initialized","thread/read"]` {
		t.Fatal(string(b))
	}
}
