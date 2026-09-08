package codex

import (
	"context"
	"fmt"
	"io"
	"os/exec"
	"regexp"
	"time"

	"requestme/internal/config"
	"requestme/internal/protocol"
)

var threadPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

type Queue struct {
	Config  config.Config
	Timeout time.Duration
}

func QueueArgs(c config.Config, a protocol.Answer) ([]string, error) {
	if !threadPattern.MatchString(a.ThreadID) || a.Text == "" {
		return nil, fmt.Errorf("invalid answer route or empty answer")
	}
	message := a.Text
	if a.RequestID != "" {
		message = "针对 request_human 请求 " + a.RequestID + " 的用户回复：\n\n" + a.Text
	}
	args := []string{"queue", "--thread", a.ThreadID, "--message", message}
	if c.AppServerURL != "" {
		args = append(args, "--remote", c.AppServerURL)
	}
	if c.AppServerTokenEnv != "" {
		args = append(args, "--remote-auth-token-env", c.AppServerTokenEnv)
	}
	return args, nil
}

func (q *Queue) Deliver(ctx context.Context, a protocol.Answer) protocol.Receipt {
	args, err := QueueArgs(q.Config, a)
	if err != nil {
		return protocol.Receipt{Status: "failed", Detail: err.Error()}
	}
	timeout := q.Timeout
	if timeout <= 0 {
		timeout = 45 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, q.Config.CodexBinary, args...)
	// CLI output may echo private user input. Receipts only contain execution facts.
	cmd.Stdout, cmd.Stderr = io.Discard, io.Discard
	if err = cmd.Start(); err != nil {
		return protocol.Receipt{Status: "failed", Detail: "could not start codex queue"}
	}
	if err = cmd.Wait(); err != nil {
		if ctx.Err() != nil {
			return protocol.Receipt{Status: "unknown", Detail: "queue interrupted or timed out; verify before resubmission"}
		}
		return protocol.Receipt{Status: "unknown", Detail: fmt.Sprintf("codex queue exit %d; verify before resubmission", cmd.ProcessState.ExitCode())}
	}
	return protocol.Receipt{Status: "accepted", Detail: "codex queue accepted the input"}
}
