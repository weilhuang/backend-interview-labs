package main

import (
	"bufio"
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

type failedWriter struct{}

func (failedWriter) Write([]byte) (int, error) { return 0, errors.New("output unavailable") }
func TestOutputFailure(t *testing.T) {
	if err := run(context.Background(), failedWriter{}); err == nil || err.Error() != "output unavailable" {
		t.Fatalf("CALLER output error lost: %v", err)
	}
}
func TestCallerHTTP(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	reader, writer := io.Pipe()
	defer reader.Close()
	done := make(chan error, 1)
	go func() { done <- run(ctx, writer); writer.Close() }()
	t.Cleanup(func() {
		cancel()
		reader.Close()
		select {
		case <-done:
		case <-time.After(10 * time.Second):
			t.Error("CALLER failed to stop owned server")
		}
	})
	line, err := bufio.NewReader(reader).ReadString('\n')
	if err != nil {
		t.Fatal(err)
	}
	url := strings.TrimSpace(strings.TrimPrefix(line, "LISTEN "))
	client := &http.Client{Timeout: 5 * time.Second}
	defer client.CloseIdleConnections()
	response, err := client.Get(url + "/healthz")
	if err != nil {
		t.Fatal(err)
	}
	body, err := io.ReadAll(response.Body)
	response.Body.Close()
	if err != nil || response.StatusCode != 200 || !strings.Contains(string(body), `"status":"ok"`) {
		t.Fatalf("CALLER bad health %v %d %s", err, response.StatusCode, body)
	}
}
