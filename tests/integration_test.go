package tests

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"requestme/internal/bridge"
	"requestme/internal/client"
	"requestme/internal/protocol"
)

type collector struct{ answers []protocol.Answer }

func (c *collector) Deliver(_ context.Context, a protocol.Answer) protocol.Receipt {
	c.answers = append(c.answers, a)
	return protocol.Receipt{Status: "accepted"}
}

func TestPythonServerGoBridge(t *testing.T) {
	python := os.Getenv("REQUEST_ME_TEST_PYTHON")
	if python == "" {
		t.Skip("set REQUEST_ME_TEST_PYTHON to run cross-language offline integration")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	root, err := filepath.Abs("..")
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.CommandContext(ctx, python, "-m", "tests.http_fixture")
	cmd.Dir = root
	cmd.Stderr = os.Stderr
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err = cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { cmd.Process.Kill(); cmd.Wait() }()
	line, err := bufio.NewReader(stdout).ReadString('\n')
	if err != nil {
		t.Fatal(err)
	}
	var port int
	if _, err = fmt.Sscanf(line, "%d", &port); err != nil {
		t.Fatal(err)
	}
	base := fmt.Sprintf("http://127.0.0.1:%d", port)
	httpClient := &http.Client{Timeout: 3 * time.Second}
	for {
		r, err := httpClient.Get(base + "/openapi.json")
		if err == nil {
			r.Body.Close()
			break
		}
		select {
		case <-ctx.Done():
			t.Fatal("fixture startup timeout")
		case <-time.After(25 * time.Millisecond):
		}
	}
	clients := []*client.Client{client.New(base, "token-one"), client.New(base, "token-two")}
	threads := []string{"01a07bde-f801-7992-bb5d-b80b58adac3f", "01a07bde-f801-7992-bb5d-b80b58adac30"}
	for i, c := range clients {
		_, err := c.Send(ctx, protocol.Message{ID: fmt.Sprintf("q%d", i), ThreadID: threads[i], Markdown: "工作已完成一部分，请补充信息。"}, true)
		if err != nil {
			t.Fatal(err)
		}
	}
	if err = clients[1].Close(ctx, "q0", threads[0]); err == nil {
		t.Fatal("foreign bridge closed request")
	}
	for _, i := range []int{1, 0} {
		body, _ := json.Marshal(map[string]string{"bridge": []string{"one", "two"}[i], "text": fmt.Sprintf("/respond q%d 人工回答%d", i, i)})
		r, err := httpClient.Post(base+"/test/answer", "application/json", bytes.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		r.Body.Close()
		if r.StatusCode != 200 {
			t.Fatalf("answer status %d", r.StatusCode)
		}
	}
	for i, c := range clients {
		d := &collector{}
		w := &bridge.Worker{API: c, Dispatcher: d}
		if err = w.Step(ctx); err != nil {
			t.Fatal(err)
		}
		if len(d.answers) != 1 || d.answers[0].ThreadID != threads[i] || d.answers[0].Text != fmt.Sprintf("人工回答%d", i) {
			t.Fatalf("misrouted: %+v", d.answers)
		}
	}
}
