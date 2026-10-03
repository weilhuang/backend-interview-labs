package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"time"

	lab "course.local/request-lifecycle"
)

func run(ctx context.Context, out io.Writer) error {
	// Own one loopback ephemeral listener. Never claim or kill an existing service.
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return err
	}
	defer listener.Close()
	server := &http.Server{
		Handler:           lab.NewHandler(&lab.MemoryStore{}, time.Second),
		ReadHeaderTimeout: 2 * time.Second, ReadTimeout: 3 * time.Second, WriteTimeout: 3 * time.Second, IdleTimeout: 10 * time.Second,
		MaxHeaderBytes: 16 << 10,
		BaseContext:    func(net.Listener) context.Context { return ctx },
	}
	if _, err = fmt.Fprintf(out, "LISTEN http://%s\n", listener.Addr()); err != nil {
		return err
	}
	stopped := make(chan struct{})
	defer close(stopped)
	finished := make(chan struct{})
	go func() {
		defer close(finished)
		select {
		case <-ctx.Done():
			shutdown, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			if server.Shutdown(shutdown) != nil {
				_ = server.Close()
			}
		case <-stopped:
		}
	}()
	err = server.Serve(listener)
	// Serve closes listener. Shutdown's context uses Background, not the canceled request root.
	if errors.Is(err, http.ErrServerClosed) {
		<-finished
		return nil
	}
	return err
}
func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	if err := run(ctx, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
