package main

import (
	"bufio"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"
)

func TestProcessHelper(t *testing.T) {
	if os.Getenv("COURSE_HTTP_HELPER") == "1" {
		main()
		os.Exit(0)
	}
}
func TestMainProcess(t *testing.T) {
	command := exec.Command(os.Args[0], "-test.run=^TestProcessHelper$")
	command.Env = append(os.Environ(), "COURSE_HTTP_HELPER=1", "GIN_MODE=release")
	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	command.Stderr = os.Stderr
	if err = command.Start(); err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 1)
	go func() { done <- command.Wait() }()
	t.Cleanup(func() {
		_ = command.Process.Signal(os.Interrupt)
		select {
		case err := <-done:
			if err != nil {
				t.Errorf("MAIN_PROCESS shutdown: %v", err)
			}
		case <-time.After(8 * time.Second):
			_ = command.Process.Kill()
			<-done
			t.Error("MAIN_PROCESS forced cleanup")
		}
	})
	lines := make(chan string, 1)
	go func() {
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			if strings.HasPrefix(scanner.Text(), "LISTEN ") {
				lines <- scanner.Text()
				return
			}
		}
		lines <- ""
	}()
	var line string
	select {
	case line = <-lines:
	case <-time.After(8 * time.Second):
		t.Fatal("MAIN_PROCESS no owned listen URL")
	}
	if line == "" {
		t.Fatal("MAIN_PROCESS missing listen URL")
	}
	client := &http.Client{Timeout: 5 * time.Second}
	defer client.CloseIdleConnections()
	response, err := client.Get(strings.TrimPrefix(line, "LISTEN ") + "/healthz")
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != 200 {
		t.Fatal(errors.New("MAIN_PROCESS health failed"))
	}
}
