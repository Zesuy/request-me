package bridge

import (
	"context"
	"errors"
	"testing"

	"requestme/internal/protocol"
)

type fakeAPI struct {
	answers     []protocol.Answer
	failReceipt bool
	receipts    []protocol.Receipt
}

func (a *fakeAPI) Answers(context.Context) ([]protocol.Answer, error) { return a.answers, nil }
func (a *fakeAPI) Receipt(_ context.Context, _ string, r protocol.Receipt) error {
	if a.failReceipt {
		return errors.New("offline")
	}
	a.receipts = append(a.receipts, r)
	return nil
}

type fakeDispatcher struct {
	calls  []protocol.Answer
	status string
}

func (d *fakeDispatcher) Deliver(_ context.Context, a protocol.Answer) protocol.Receipt {
	d.calls = append(d.calls, a)
	return protocol.Receipt{Status: d.status}
}

func TestLostReceiptDoesNotReplay(t *testing.T) {
	a := &fakeAPI{answers: []protocol.Answer{{ID: "a", RequestID: "q", ThreadID: "thread", Text: "reply"}}, failReceipt: true}
	d := &fakeDispatcher{status: "accepted"}
	w := &Worker{API: a, Dispatcher: d}
	if w.Step(context.Background()) == nil {
		t.Fatal("expected receipt error")
	}
	a.failReceipt = false
	if err := w.Step(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(d.calls) != 1 {
		t.Fatalf("queue repeated %d times", len(d.calls))
	}
}

func TestMixedSessionsAndUnknown(t *testing.T) {
	a := &fakeAPI{answers: []protocol.Answer{{ID: "a", RequestID: "q1", ThreadID: "one", Text: "A"}, {ID: "b", RequestID: "q2", ThreadID: "two", Text: "B"}}}
	d := &fakeDispatcher{status: "unknown"}
	w := &Worker{API: a, Dispatcher: d}
	for range 2 {
		if err := w.Step(context.Background()); err != nil {
			t.Fatal(err)
		}
	}
	if len(d.calls) != 2 || d.calls[0].ThreadID != "one" || d.calls[1].Text != "B" {
		t.Fatalf("wrong routing: %+v", d.calls)
	}
}
