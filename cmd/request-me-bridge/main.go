package main

import (
	"context"
	"flag"
	"log"
	"os"
	"os/signal"

	"requestme/internal/bridge"
	"requestme/internal/client"
	"requestme/internal/codex"
	"requestme/internal/config"
)

func main() {
	path := flag.String("config", "bridge.local.json", "configuration file")
	once := flag.Bool("once", false, "perform one long-poll cycle then exit")
	flag.Parse()
	c, err := config.Load(*path)
	if err != nil {
		log.Fatal(err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	w := &bridge.Worker{API: client.New(c.ServerURL, os.Getenv(c.TokenEnv)), Dispatcher: &codex.Queue{Config: c}}
	if *once {
		err = w.Step(ctx)
	} else {
		err = w.Run(ctx)
	}
	if err != nil && ctx.Err() == nil {
		log.Fatal(err)
	}
}
