package config

import (
	"encoding/json"
	"errors"
	"net/url"
	"os"
	"strings"
)

// Config is shared by the two independently deployed Go programs.
// A token maps to a bridge identity on the server; IDs never come from the model.
type Config struct {
	ServerURL         string `json:"server_url"`
	TokenEnv          string `json:"token_env"`
	HostLabel         string `json:"host_label"`
	CodexBinary       string `json:"codex_binary"`
	AppServerURL      string `json:"app_server_url"`
	AppServerTokenEnv string `json:"app_server_token_env,omitempty"`
}

func Load(path string) (Config, error) {
	var c Config
	b, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	if err = json.Unmarshal(b, &c); err != nil {
		return c, err
	}
	u, err := url.Parse(c.ServerURL)
	if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return c, errors.New("server_url must be an HTTP(S) origin without credentials, query or fragment")
	}
	c.ServerURL = strings.TrimRight(c.ServerURL, "/")
	if c.TokenEnv == "" || os.Getenv(c.TokenEnv) == "" {
		return c, errors.New("token_env must name a nonempty environment variable")
	}
	if c.CodexBinary == "" {
		c.CodexBinary = "codex"
	}
	if c.HostLabel == "" {
		c.HostLabel, _ = os.Hostname()
	}
	return c, nil
}
