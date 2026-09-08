package codex

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"time"

	"github.com/gorilla/websocket"
	"requestme/internal/protocol"
)

type Reader struct{ Endpoint, TokenEnv string }

func NewReader(endpoint, tokenEnv string) *Reader { return &Reader{endpoint, tokenEnv} }

// Source performs read-only enrichment against the owning app-server.
// A fresh connection avoids subscriptions and sharing RPC state across MCP calls.
func (r *Reader) Source(ctx context.Context, threadID string) (protocol.Source, error) {
	var source protocol.Source
	if !threadPattern.MatchString(threadID) {
		return source, fmt.Errorf("invalid thread id")
	}
	if r.Endpoint == "" {
		return source, fmt.Errorf("app-server endpoint not configured")
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	u, err := url.Parse(r.Endpoint)
	if err != nil {
		return source, err
	}
	dialer := websocket.Dialer{HandshakeTimeout: 5 * time.Second}
	endpoint := r.Endpoint
	if u.Scheme == "unix" {
		path := u.Path
		if path == "" {
			return source, fmt.Errorf("explicit unix socket path required")
		}
		dialer.NetDialContext = func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", path)
		}
		endpoint = "ws://localhost/"
	} else if u.Scheme != "ws" && u.Scheme != "wss" {
		return source, fmt.Errorf("unsupported app-server endpoint")
	}
	headers := http.Header{}
	if r.TokenEnv != "" {
		token := os.Getenv(r.TokenEnv)
		if token == "" {
			return source, fmt.Errorf("app-server token environment variable is empty")
		}
		headers.Set("Authorization", "Bearer "+token)
	}
	conn, resp, err := dialer.DialContext(ctx, endpoint, headers)
	if err != nil {
		if resp != nil {
			resp.Body.Close()
		}
		return source, fmt.Errorf("app-server connection failed")
	}
	defer conn.Close()
	deadline, _ := ctx.Deadline()
	conn.SetReadDeadline(deadline)
	conn.SetWriteDeadline(deadline)
	rpc := func(id int, method string, params any, result any) error {
		if err := conn.WriteJSON(map[string]any{"id": id, "method": method, "params": params}); err != nil {
			return err
		}
		for {
			var msg struct {
				ID     *int            `json:"id"`
				Result json.RawMessage `json:"result"`
				Error  json.RawMessage `json:"error"`
			}
			if err := conn.ReadJSON(&msg); err != nil {
				return err
			}
			if msg.ID == nil || *msg.ID != id {
				continue
			}
			if len(msg.Error) > 0 && string(msg.Error) != "null" {
				return fmt.Errorf("app-server %s failed", method)
			}
			if result != nil {
				return json.Unmarshal(msg.Result, result)
			}
			return nil
		}
	}
	if err = rpc(1, "initialize", map[string]any{"clientInfo": map[string]string{"name": "request_me", "version": "0.1.0"}}, nil); err != nil {
		return source, err
	}
	if err = conn.WriteJSON(map[string]any{"method": "initialized", "params": map[string]any{}}); err != nil {
		return source, err
	}
	var result struct {
		Thread struct {
			ID   string `json:"id"`
			Name string `json:"name"`
			CWD  string `json:"cwd"`
		} `json:"thread"`
	}
	if err = rpc(2, "thread/read", map[string]any{"threadId": threadID, "includeTurns": false}, &result); err != nil {
		return source, err
	}
	if result.Thread.ID != threadID {
		return source, fmt.Errorf("app-server returned a different thread")
	}
	return protocol.Source{Title: result.Thread.Name, CWD: result.Thread.CWD}, nil
}
