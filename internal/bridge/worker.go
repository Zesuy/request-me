package bridge

import (
	"context"
	"fmt"
	"log"
	"time"

	"requestme/internal/protocol"
)

type API interface {
	Answers(context.Context) ([]protocol.Answer, error)
	Receipt(context.Context, string, protocol.Receipt) error
}

type Dispatcher interface {
	Deliver(context.Context, protocol.Answer) protocol.Receipt
}

// Worker is single-consumer. Its in-memory journal prevents duplicate dispatch
// during this process lifetime, including a lost receipt response.
type Worker struct {
	API        API
	Dispatcher Dispatcher
	seen       map[string]protocol.Receipt
	awaiting   map[string]protocol.Receipt
}

func (w *Worker) flush(ctx context.Context) error {
	for id, receipt := range w.awaiting {
		if err := w.API.Receipt(ctx, id, receipt); err != nil {
			return err
		}
		delete(w.awaiting, id)
	}
	return nil
}

func (w *Worker) Step(ctx context.Context) error {
	if w.seen == nil {
		w.seen = make(map[string]protocol.Receipt)
		w.awaiting = make(map[string]protocol.Receipt)
	}
	if err := w.flush(ctx); err != nil {
		return err
	}
	answers, err := w.API.Answers(ctx)
	if err != nil {
		return err
	}
	for _, a := range answers {
		if a.ID == "" || a.RequestID == "" {
			return fmt.Errorf("server returned an answer without an identity")
		}
		receipt, exists := w.seen[a.ID]
		if !exists {
			receipt = w.Dispatcher.Deliver(ctx, a)
			w.seen[a.ID] = receipt
		}
		w.awaiting[a.ID] = receipt
	}
	return w.flush(ctx)
}

func (w *Worker) Run(ctx context.Context) error {
	delay := time.Second
	for ctx.Err() == nil {
		if err := w.Step(ctx); err != nil {
			if ctx.Err() != nil {
				break
			}
			log.Printf("bridge cycle failed: %v", err)
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(delay):
			}
			if delay < 30*time.Second {
				delay *= 2
				if delay > 30*time.Second {
					delay = 30 * time.Second
				}
			}
		} else {
			delay = time.Second
		}
	}
	return ctx.Err()
}
