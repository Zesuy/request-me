package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"requestme/internal/client"
	"requestme/internal/codex"
	"requestme/internal/config"
	"requestme/internal/mcpserver"
)

func main() {
	path := flag.String("config", "bridge.local.json", "JSON configuration file")
	flag.Parse()
	c, err := config.Load(*path)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	token := os.Getenv(c.TokenEnv)
	bridge := mcpserver.New(client.New(c.ServerURL, token), c.HostLabel, codex.NewReader(c.AppServerURL, c.AppServerTokenEnv))
	server := mcp.NewServer(&mcp.Implementation{Name: "request-me", Version: "0.1.0"}, nil)
	bridge.Install(server)
	if err := server.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
		log.Fatal(err)
	}
}
