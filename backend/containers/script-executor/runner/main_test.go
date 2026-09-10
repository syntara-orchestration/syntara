package main

import (
	"bufio"
	"strings"
	"testing"
	"time"
)

func TestRunBash(t *testing.T) {
	runtimeLanguage = "bash"
	response := run([]byte(`{"code":"echo hello-$NAME","environment":{"NAME":"Ada"}}`), time.Minute, 1024)
	if !response.OK || response.Stdout != "hello-Ada\n" || response.ReturnCode != 0 {
		t.Fatalf("unexpected response: %#v", response)
	}
}

func TestRunPythonParsesFinalJSONLine(t *testing.T) {
	runtimeLanguage = "python"
	response := run([]byte(`{"code":"import json; print('debug'); print(json.dumps({'answer': 42}))"}`), time.Minute, 1024)
	if !response.OK || response.StdoutJSON == nil {
		t.Fatalf("unexpected response: %#v", response)
	}
	value, ok := response.StdoutJSON.(map[string]any)
	if !ok || value["answer"] != float64(42) {
		t.Fatalf("unexpected JSON output: %#v", response.StdoutJSON)
	}
}

func TestRunRejectsReservedEnvironment(t *testing.T) {
	response := run([]byte(`{"code":"echo hello","environment":{"LD_PRELOAD":"evil.so"}}`), time.Minute, 1024)
	if response.OK || response.ErrorType != "ValidationError" {
		t.Fatalf("unexpected response: %#v", response)
	}
}

func TestRunRejectsMultipleJSONValues(t *testing.T) {
	response := run([]byte(`{"code":"echo hello"}{"code":"echo again"}`), time.Minute, 1024)
	if response.OK || response.ErrorType != "ValidationError" {
		t.Fatalf("unexpected response: %#v", response)
	}
}

func TestRunTimesOutAndKillsScript(t *testing.T) {
	runtimeLanguage = "bash"
	response := run([]byte(`{"code":"sleep 10","timeout_seconds":0.05}`), time.Minute, 1024)
	if response.OK || response.ErrorType != "TimeoutError" {
		t.Fatalf("unexpected response: %#v", response)
	}
}

func TestReadLineRejectsOversizedInput(t *testing.T) {
	reader := bufio.NewReaderSize(strings.NewReader(strings.Repeat("x", maxInputBytes+1)+"\n"), maxInputBytes+1)
	_, err := readLine(reader)
	if err == nil || !strings.Contains(err.Error(), "input limit") {
		t.Fatalf("unexpected error: %v", err)
	}
}
