// dispatcher-poc proves the Kubernetes pods/exec path through a Receptor TCP bridge.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
)

const defaultCommand = `{"method":"GET","url":"https://example.com","timeout_seconds":10}`

type output struct {
	OK     bool            `json:"ok"`
	Result json.RawMessage `json:"result,omitempty"`
	Error  string          `json:"error,omitempty"`
}

func main() {
	var (
		executionNamespace = flag.String("execution-namespace", "syntara-execution-poc", "namespace containing the warm executor")
		workerSelector     = flag.String("worker-selector", "app=http-executor-worker", "label selector for the warm executor")
		receptorAddress    = flag.String("receptor-address", "receptor-hub.syntara-control-poc.svc:9443", "Receptor TCP door; the only TCP destination used for Kubernetes calls")
		command            = flag.String("command", defaultCommand, "one JSON object to send to executor stdin")
		timeout            = flag.Duration("timeout", 45*time.Second, "whole POC timeout")
	)
	flag.Parse()

	result, err := run(context.Background(), *executionNamespace, *workerSelector, *receptorAddress, *command, *timeout)
	if err != nil {
		write(output{OK: false, Error: err.Error()})
		os.Exit(1)
	}
	write(output{OK: true, Result: result})
}

func run(parent context.Context, namespace, selector, receptorAddress, command string, timeout time.Duration) (json.RawMessage, error) {
	var request map[string]any
	if err := json.Unmarshal([]byte(command), &request); err != nil || request == nil {
		return nil, fmt.Errorf("command must be one valid JSON object")
	}

	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()

	config, err := rest.InClusterConfig()
	if err != nil {
		return nil, fmt.Errorf("load in-cluster Kubernetes configuration: %w", err)
	}
	// Keep config.Host as kubernetes.default.svc.  It supplies the correct API
	// hostname and TLS SNI; only the TCP connection is sent to Receptor.
	config.Dial = receptorDialer(receptorAddress)

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("create Kubernetes client: %w", err)
	}
	pod, err := oneRunningPod(ctx, clientset, namespace, selector)
	if err != nil {
		return nil, err
	}

	req := clientset.CoreV1().RESTClient().Post().Namespace(namespace).Resource("pods").Name(pod.Name).SubResource("exec")
	req.VersionedParams(&corev1.PodExecOptions{
		Container: "http-executor",
		Command:   []string{"python", "-m", "syntara.http_executor"},
		Stdin:     true,
		Stdout:    true,
		Stderr:    true,
		TTY:       false,
	}, scheme.ParameterCodec)

	executor, err := remotecommand.NewSPDYExecutor(config, http.MethodPost, req.URL())
	if err != nil {
		return nil, fmt.Errorf("create pods/exec stream: %w", err)
	}
	var stdout, stderr bytes.Buffer
	err = executor.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdin:  strings.NewReader(command + "\n"),
		Stdout: &stdout,
		Stderr: &stderr,
		Tty:    false,
	})
	if err != nil {
		return nil, fmt.Errorf("run pods/exec: %w; stderr: %s", err, strings.TrimSpace(stderr.String()))
	}
	if text := strings.TrimSpace(stderr.String()); text != "" {
		return nil, fmt.Errorf("executor wrote stderr: %s", text)
	}
	return oneJSONLine(stdout.String())
}

func receptorDialer(address string) func(context.Context, string, string) (net.Conn, error) {
	dialer := &net.Dialer{}
	return func(ctx context.Context, network, _ string) (net.Conn, error) {
		return dialer.DialContext(ctx, network, address)
	}
}

func oneRunningPod(ctx context.Context, clientset kubernetes.Interface, namespace, selector string) (*corev1.Pod, error) {
	pods, err := clientset.CoreV1().Pods(namespace).List(ctx, metav1.ListOptions{LabelSelector: selector})
	if err != nil {
		return nil, fmt.Errorf("list executor pods: %w", err)
	}
	var running []*corev1.Pod
	for i := range pods.Items {
		if pods.Items[i].Status.Phase == corev1.PodRunning {
			running = append(running, &pods.Items[i])
		}
	}
	if len(running) != 1 {
		return nil, fmt.Errorf("need exactly one running executor pod matching %q, found %d", selector, len(running))
	}
	return running[0], nil
}

func oneJSONLine(stdout string) (json.RawMessage, error) {
	lines := strings.Split(strings.TrimSpace(stdout), "\n")
	if len(lines) != 1 || !json.Valid([]byte(lines[0])) {
		return nil, fmt.Errorf("executor stdout must contain exactly one JSON line")
	}
	var value any
	if err := json.Unmarshal([]byte(lines[0]), &value); err != nil {
		return nil, fmt.Errorf("decode executor result: %w", err)
	}
	if _, isObject := value.(map[string]any); !isObject {
		return nil, fmt.Errorf("executor result must be a JSON object")
	}
	return json.RawMessage(lines[0]), nil
}

func write(value output) {
	encoded, err := json.Marshal(value)
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal result: %v\n", err)
		return
	}
	fmt.Println(string(encoded))
}
