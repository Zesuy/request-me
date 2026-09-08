package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"requestme/internal/protocol"
)

type Client struct {
	BaseURL, Token string
	HTTP           *http.Client
}

func New(baseURL, token string) *Client {
	return &Client{baseURL, token, &http.Client{Timeout: 40 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}
}

func (c *Client) call(ctx context.Context, method, path string, body, out any) error {
	var data []byte
	var err error
	if body != nil {
		data, err = json.Marshal(body)
		if err != nil {
			return err
		}
	}
	r, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, bytes.NewReader(data))
	if err != nil {
		return err
	}
	r.Header.Set("Authorization", "Bearer "+c.Token)
	r.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTP.Do(r)
	if err != nil {
		return fmt.Errorf("request-me transport failed (%T)", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("request-me returned HTTP %d", resp.StatusCode)
	}
	if out == nil {
		return nil
	}
	return json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(out)
}

func (c *Client) Send(ctx context.Context, m protocol.Message, human bool) (protocol.Sent, error) {
	path := "/v1/notifications"
	if human {
		path = "/v1/requests"
	}
	var out protocol.Sent
	err := c.call(ctx, "POST", path, m, &out)
	if err == nil && (out.ID != m.ID || out.Status != "sent") {
		err = fmt.Errorf("server did not confirm message sent")
	}
	return out, err
}

func (c *Client) Close(ctx context.Context, id, thread string) error {
	return c.call(ctx, "POST", "/v1/requests/"+url.PathEscape(id)+"/close", map[string]string{"thread_id": thread}, nil)
}

func (c *Client) Answers(ctx context.Context) ([]protocol.Answer, error) {
	var out struct {
		Answers []protocol.Answer `json:"answers"`
	}
	err := c.call(ctx, "GET", "/v1/answers?wait=25", nil, &out)
	return out.Answers, err
}

func (c *Client) Receipt(ctx context.Context, id string, receipt protocol.Receipt) error {
	return c.call(ctx, "POST", "/v1/answers/"+url.PathEscape(id)+"/receipt", receipt, nil)
}
