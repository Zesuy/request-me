package mcpserver

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"requestme/internal/client"
	"requestme/internal/protocol"
)

// SourceResolver optionally enriches messages with the owning Codex session.
// Implementations may query app-server; failures fall back to the local host.
type SourceResolver interface {
	Source(context.Context, string) (protocol.Source, error)
}

type Server struct {
	client  *client.Client
	host    string
	resolve SourceResolver
}

func New(c *client.Client, host string, resolver SourceResolver) *Server {
	if host == "" {
		host, _ = os.Hostname()
	}
	return &Server{client: c, host: host, resolve: resolver}
}

type requestInput struct {
	Markdown string            `json:"markdown"`
	Options  []protocol.Option `json:"options,omitempty"`
}
type notifyInput struct {
	Markdown string `json:"markdown"`
}
type closeInput struct {
	RequestID string `json:"request_id"`
}

// Codex identifiers are UUID-shaped but are not required to use RFC 4122
// version/variant bits, so validate their shape without imposing those bits.
var uuidRE = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

func routing(req *mcp.CallToolRequest) (string, string, error) {
	if req == nil || req.Params == nil {
		return "", "", fmt.Errorf("per-call metadata is required")
	}
	m := req.Params.Meta
	var direct, nested string
	if m != nil {
		if v, ok := m["threadId"].(string); ok {
			direct = v
		}
		if v, ok := m["x-codex-turn-metadata"].(map[string]any); ok {
			if x, ok := v["thread_id"].(string); ok {
				nested = x
			}
		}
		if v, ok := m["x-codex-turn-metadata"].(string); ok {
			var x map[string]any
			if json.Unmarshal([]byte(v), &x) == nil {
				if z, ok := x["thread_id"].(string); ok {
					nested = z
				}
			}
		}
	}
	direct, nested = strings.ToLower(direct), strings.ToLower(nested)
	if direct != "" && nested != "" && direct != nested {
		return "", "", fmt.Errorf("conflicting thread identifiers")
	}
	id := direct
	if id == "" {
		id = nested
	}
	if !uuidRE.MatchString(id) {
		return "", "", fmt.Errorf("a concrete UUID threadId is required in _meta")
	}
	callID := ""
	if m != nil {
		if v, ok := m["callId"].(string); ok {
			callID = v
		}
	}
	return id, callID, nil
}

func messageID(thread, callID, tool string) string {
	if callID == "" {
		var b [16]byte
		if _, err := rand.Read(b[:]); err == nil {
			return hex.EncodeToString(b[:])
		}
	}
	h := sha256.Sum256([]byte(thread + "\x00" + callID + "\x00" + tool))
	return hex.EncodeToString(h[:])
}

func (s *Server) source(ctx context.Context, thread string) protocol.Source {
	if s.resolve != nil {
		if src, err := s.resolve.Source(ctx, thread); err == nil {
			if src.Host == "" {
				src.Host = s.host
			}
			return src
		}
	}
	// MCP process cwd may differ from a remote task's execution cwd.
	// Omit unverified directory information rather than mislabel the source.
	return protocol.Source{Host: s.host}
}

func result(v any) (*mcp.CallToolResult, any, error) {
	b, _ := json.Marshal(v)
	return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: string(b)}}, StructuredContent: v}, v, nil
}
func failure(err error) (*mcp.CallToolResult, any, error) { return nil, nil, err }

func (s *Server) RequestHuman(ctx context.Context, req *mcp.CallToolRequest, in requestInput) (*mcp.CallToolResult, any, error) {
	thread, call, err := routing(req)
	if err != nil {
		return failure(err)
	}
	if strings.TrimSpace(in.Markdown) == "" {
		return failure(fmt.Errorf("markdown is required"))
	}
	id := messageID(thread, call, "request_human")
	msg := protocol.Message{ID: id, ThreadID: thread, Markdown: in.Markdown, Options: in.Options, Source: s.source(ctx, thread)}
	sent, err := s.client.Send(ctx, msg, true)
	if err != nil {
		return failure(err)
	}
	return result(sent)
}

func (s *Server) Notify(ctx context.Context, req *mcp.CallToolRequest, in notifyInput) (*mcp.CallToolResult, any, error) {
	thread, call, err := routing(req)
	if err != nil {
		return failure(err)
	}
	if strings.TrimSpace(in.Markdown) == "" {
		return failure(fmt.Errorf("markdown is required"))
	}
	id := messageID(thread, call, "notify")
	msg := protocol.Message{ID: id, ThreadID: thread, Markdown: in.Markdown, Source: s.source(ctx, thread)}
	sent, err := s.client.Send(ctx, msg, false)
	if err != nil {
		return failure(err)
	}
	return result(sent)
}

func (s *Server) CloseRequest(ctx context.Context, req *mcp.CallToolRequest, in closeInput) (*mcp.CallToolResult, any, error) {
	thread, _, err := routing(req)
	if err != nil {
		return failure(err)
	}
	if strings.TrimSpace(in.RequestID) == "" || strings.ContainsAny(in.RequestID, "/\\") {
		return failure(fmt.Errorf("request_id is required"))
	}
	if err := s.client.Close(ctx, in.RequestID, thread); err != nil {
		return failure(err)
	}
	return result(protocol.Receipt{Status: "closed"})
}

func (s *Server) Install(server *mcp.Server) {
	mcp.AddTool(server, &mcp.Tool{Name: "request_user_response", Description: "Send a question to the user through their configured external messaging channel when work needs information, a decision, or confirmation that a physical action is complete. Write Markdown explaining work done, important findings, attempts, and the help needed. Optional choices contain id, label and the user's answer value; free text is always available. A sent receipt means the channel accepted the message. After sent success, finish the current turn. The user's response later arrives as a new user turn in this same task; continue the work using that response. Silence leaves the request pending."}, s.RequestHuman)
	mcp.AddTool(server, &mcp.Tool{Name: "send_user_notification", Description: "Send a progress update or result to the user through their configured external messaging channel. A sent receipt means the channel accepted the message. Continue the current work after sending; finish only when the task is complete. When progress depends on the user's information, decision, or action, use request_user_response to create an answerable request."}, s.Notify)
	mcp.AddTool(server, &mcp.Tool{Name: "close_user_request", Description: "Close a previously sent user request that has been resolved or is no longer needed. Use the request_id returned by request_user_response. Closing removes the pending question while preserving the original task; it does not enqueue a user message or start a new turn."}, s.CloseRequest)
}
