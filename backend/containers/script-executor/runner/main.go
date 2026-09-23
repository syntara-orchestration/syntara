// script-executor runs one untrusted Bash or Python program per JSONL command.
package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"syscall"
	"time"
)

const (
	maxInputBytes       = 1 << 20
	maxCodeBytes        = 256 << 10
	maxEnvironmentItems = 100
	maxEnvironmentBytes = 64 << 10
	defaultTimeout      = 300 * time.Second
	defaultOutputBytes  = 1 << 20
)

// runtimeLanguage is set at image build time to bash or python.
var runtimeLanguage = ""

var environmentName = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

type command struct {
	Code           string         `json:"code"`
	Environment    map[string]any `json:"environment"`
	TimeoutSeconds *float64       `json:"timeout_seconds"`
}

type result struct {
	OK              bool    `json:"ok"`
	ReturnCode      int     `json:"return_code"`
	Stdout          string  `json:"stdout"`
	Stderr          string  `json:"stderr"`
	StdoutTruncated bool    `json:"stdout_truncated,omitempty"`
	StderrTruncated bool    `json:"stderr_truncated,omitempty"`
	StdoutJSON      any     `json:"stdout_json,omitempty"`
	Elapsed         float64 `json:"elapsed"`
	ErrorType       string  `json:"error_type,omitempty"`
	Message         string  `json:"message,omitempty"`
}

type commandError struct {
	kind    string
	message string
}

func (e *commandError) Error() string { return e.message }

func main() {
	once := flag.Bool("once", false, "exit when stdin reaches EOF even if idle mode is enabled")
	flag.Parse()
	if runtimeLanguage != "bash" && runtimeLanguage != "python" {
		fmt.Fprintln(os.Stderr, "script executor image has no configured runtime")
		os.Exit(1)
	}
	maxTimeout := durationFromEnvironment("SCRIPT_EXECUTOR_MAX_TIMEOUT_SECONDS", defaultTimeout)
	maxOutput := bytesFromEnvironment("SCRIPT_EXECUTOR_MAX_OUTPUT_BYTES", defaultOutputBytes)
	keepAlive := os.Getenv("SCRIPT_EXECUTOR_KEEP_ALIVE") == "true" && !*once
	reader := bufio.NewReaderSize(os.Stdin, maxInputBytes+1)
	for {
		line, err := readLine(reader)
		if err == io.EOF && len(line) == 0 {
			if !keepAlive {
				return
			}
			time.Sleep(time.Second)
			continue
		}
		if err != nil {
			write(result{OK: false, ErrorType: "ValidationError", Message: err.Error()})
			if err == io.EOF {
				return
			}
			continue
		}
		if len(bytes.TrimSpace(line)) == 0 {
			continue
		}
		write(run(line, maxTimeout, maxOutput))
	}
}

func readLine(reader *bufio.Reader) ([]byte, error) {
	line, err := reader.ReadSlice('\n')
	if errors.Is(err, bufio.ErrBufferFull) {
		for errors.Is(err, bufio.ErrBufferFull) {
			_, err = reader.ReadSlice('\n')
		}
		return nil, &commandError{"ValidationError", "command exceeds the 1 MiB input limit"}
	}
	if len(line) > maxInputBytes {
		return nil, &commandError{"ValidationError", "command exceeds the 1 MiB input limit"}
	}
	if err != nil && !errors.Is(err, io.EOF) {
		return nil, err
	}
	return line, err
}

func run(line []byte, maxTimeout time.Duration, maxOutput int) result {
	started := time.Now()
	request, err := parseCommand(line, maxTimeout)
	if err != nil {
		var inputErr *commandError
		if errors.As(err, &inputErr) {
			return result{OK: false, ErrorType: inputErr.kind, Message: inputErr.message}
		}
		return result{OK: false, ErrorType: "ValidationError", Message: "command must be valid JSON"}
	}

	stdout, stderr, exitCode, timedOut, stdoutTruncated, stderrTruncated, err := execute(request, maxOutput)
	response := result{
		OK:              err == nil && !timedOut && exitCode == 0,
		ReturnCode:      exitCode,
		Stdout:          string(stdout),
		Stderr:          string(stderr),
		StdoutTruncated: stdoutTruncated,
		StderrTruncated: stderrTruncated,
		Elapsed:         time.Since(started).Seconds(),
	}
	if timedOut {
		response.ErrorType = "TimeoutError"
		response.Message = "script execution timed out"
	} else if err != nil {
		response.ErrorType = "ExecutionError"
		response.Message = "script could not be started"
	} else if exitCode != 0 {
		response.ErrorType = "ScriptExecutionError"
		response.Message = fmt.Sprintf("script failed with exit code %d", exitCode)
	}
	if runtimeLanguage == "python" && response.OK {
		response.StdoutJSON = parsePythonJSON(response.Stdout)
	}
	return response
}

func parseCommand(line []byte, maxTimeout time.Duration) (command, error) {
	var value command
	decoder := json.NewDecoder(bytes.NewReader(line))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&value); err != nil {
		return command{}, err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return command{}, &commandError{"ValidationError", "command must contain exactly one JSON object"}
	}
	if value.Code == "" || len([]byte(value.Code)) > maxCodeBytes {
		return command{}, &commandError{"ValidationError", "code must be non-empty and no more than 256 KiB"}
	}
	if len(value.Environment) > maxEnvironmentItems {
		return command{}, &commandError{"ValidationError", "environment cannot contain more than 100 entries"}
	}
	environmentBytes := 0
	for key, rawValue := range value.Environment {
		if !environmentName.MatchString(key) || isReservedEnvironmentName(key) {
			return command{}, &commandError{"ValidationError", "environment contains a reserved or invalid variable name"}
		}
		if rawValue == nil {
			return command{}, &commandError{"ValidationError", "environment values cannot be null"}
		}
		encoded, err := environmentValue(rawValue)
		if err != nil || strings.ContainsRune(encoded, '\x00') {
			return command{}, &commandError{"ValidationError", "environment values must be scalar values without null bytes"}
		}
		environmentBytes += len(key) + len(encoded)
	}
	if environmentBytes > maxEnvironmentBytes {
		return command{}, &commandError{"ValidationError", "environment exceeds the 64 KiB limit"}
	}
	if value.TimeoutSeconds != nil {
		if *value.TimeoutSeconds <= 0 || time.Duration(*value.TimeoutSeconds*float64(time.Second)) > maxTimeout {
			return command{}, &commandError{"ValidationError", "timeout_seconds exceeds the configured limit"}
		}
	}
	return value, nil
}

func environmentValue(value any) (string, error) {
	switch typed := value.(type) {
	case string:
		return typed, nil
	case bool, float64:
		return fmt.Sprint(typed), nil
	default:
		return "", errors.New("not a scalar")
	}
}

func isReservedEnvironmentName(name string) bool {
	return name == "PATH" || name == "HOME" || name == "TMP" || name == "TEMP" || name == "TMPDIR" ||
		name == "IFS" || name == "ENV" || name == "BASH_ENV" || strings.HasPrefix(name, "LD_") ||
		strings.HasPrefix(name, "DYLD_") || strings.HasPrefix(name, "PYTHON")
}

func execute(request command, maxOutput int) ([]byte, []byte, int, bool, bool, bool, error) {
	timeout := defaultTimeout
	if request.TimeoutSeconds != nil {
		timeout = time.Duration(*request.TimeoutSeconds * float64(time.Second))
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	var cmd *exec.Cmd
	if runtimeLanguage == "bash" {
		cmd = exec.Command("/bin/bash", "--noprofile", "--norc", "-c", request.Code)
	} else {
		cmd = exec.Command("/usr/bin/python3", "-I", "-B", "-c", request.Code)
	}
	cmd.Dir = "/"
	cmd.Env = safeEnvironment(request.Environment)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	stdoutPipe, err := cmd.StdoutPipe()
	if err != nil {
		return nil, nil, -1, false, false, false, err
	}
	stderrPipe, err := cmd.StderrPipe()
	if err != nil {
		return nil, nil, -1, false, false, false, err
	}
	if err := cmd.Start(); err != nil {
		return nil, nil, -1, false, false, false, err
	}
	stdoutDone := make(chan limitedOutput, 1)
	stderrDone := make(chan limitedOutput, 1)
	go func() { stdoutDone <- readLimited(stdoutPipe, maxOutput) }()
	go func() { stderrDone <- readLimited(stderrPipe, maxOutput) }()
	waitDone := make(chan error, 1)
	go func() { waitDone <- cmd.Wait() }()

	timedOut := false
	var waitErr error
	select {
	case waitErr = <-waitDone:
	case <-ctx.Done():
		timedOut = true
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		waitErr = <-waitDone
	}
	stdout := <-stdoutDone
	stderr := <-stderrDone
	exitCode := 0
	if waitErr != nil {
		if exitError, ok := waitErr.(*exec.ExitError); ok {
			exitCode = exitError.ExitCode()
		} else if !timedOut {
			return stdout.data, stderr.data, -1, false, stdout.truncated, stderr.truncated, waitErr
		}
	}
	return stdout.data, stderr.data, exitCode, timedOut, stdout.truncated, stderr.truncated, nil
}

type limitedOutput struct {
	data      []byte
	truncated bool
}

func readLimited(reader io.Reader, max int) limitedOutput {
	data, _ := io.ReadAll(io.LimitReader(reader, int64(max)+1))
	if len(data) <= max {
		return limitedOutput{data: data}
	}
	_, _ = io.Copy(io.Discard, reader)
	return limitedOutput{data: data[:max], truncated: true}
}

func safeEnvironment(request map[string]any) []string {
	environment := []string{
		"PATH=/usr/bin:/bin",
		"HOME=/nonexistent",
		"TMPDIR=/nonexistent",
		"TMP=/nonexistent",
		"TEMP=/nonexistent",
		"LANG=C.UTF-8",
		"LC_ALL=C.UTF-8",
		"PYTHONDONTWRITEBYTECODE=1",
		"PYTHONNOUSERSITE=1",
	}
	for key, rawValue := range request {
		value, _ := environmentValue(rawValue)
		environment = append(environment, key+"="+value)
	}
	return environment
}

func parsePythonJSON(stdout string) any {
	trimmed := strings.TrimSpace(stdout)
	if trimmed == "" {
		return nil
	}
	var value any
	if json.Unmarshal([]byte(trimmed), &value) == nil {
		return value
	}
	lines := strings.Split(trimmed, "\n")
	if len(lines) > 0 && json.Unmarshal([]byte(lines[len(lines)-1]), &value) == nil {
		return value
	}
	return nil
}

func durationFromEnvironment(name string, fallback time.Duration) time.Duration {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	var seconds float64
	if _, err := fmt.Sscanf(value, "%f", &seconds); err != nil || seconds <= 0 {
		return fallback
	}
	return time.Duration(seconds * float64(time.Second))
}

func bytesFromEnvironment(name string, fallback int) int {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	var parsed int
	if _, err := fmt.Sscanf(value, "%d", &parsed); err != nil || parsed <= 0 {
		return fallback
	}
	return parsed
}

func write(value result) {
	encoded, err := json.Marshal(value)
	if err != nil {
		encoded = []byte(`{"ok":false,"error_type":"InternalError","message":"could not encode result"}`)
	}
	fmt.Println(string(encoded))
}
