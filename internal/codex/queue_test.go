package codex

import (
	"context"
	"reflect"
	"testing"

	"requestme/internal/config"
	"requestme/internal/protocol"
)

const testThread = "01a07bde-f801-7992-bb5d-b80b58adac3f"

func TestQueueArgsPreserveInput(t *testing.T) {
	text := "--help ; $(something)\n你好"
	c := config.Config{AppServerURL: "unix:///tmp/control.sock", AppServerTokenEnv: "REMOTE_TOKEN"}
	args, err := QueueArgs(c, protocol.Answer{ThreadID: testThread, Text: text})
	want := []string{"queue", "--thread", testThread, "--message", text, "--remote", c.AppServerURL, "--remote-auth-token-env", "REMOTE_TOKEN"}
	if err != nil || !reflect.DeepEqual(args, want) {
		t.Fatalf("%v %v", args, err)
	}
}

func TestQueueInvalidAndMissingExecutable(t *testing.T) {
	q := &Queue{Config: config.Config{CodexBinary: "__missing_request_me_binary__"}}
	for _, id := range []string{"bad", testThread} {
		r := q.Deliver(context.Background(), protocol.Answer{ThreadID: id, Text: "answer"})
		if r.Status != "failed" {
			t.Fatal(r)
		}
	}
}

func TestQueueIncludesQuestionAssociation(t *testing.T) {
	args, err := QueueArgs(config.Config{}, protocol.Answer{RequestID: "question-2", ThreadID: testThread, Text: "继续"})
	if err != nil || args[4] != "针对 request_human 请求 question-2 的用户回复：\n\n继续" {
		t.Fatalf("%v %v", args, err)
	}
}
