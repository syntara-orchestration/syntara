package main

import "testing"

func TestOneJSONLine(t *testing.T) {
	value, err := oneJSONLine("{\"ok\":true}\n")
	if err != nil || string(value) != `{"ok":true}` {
		t.Fatalf("oneJSONLine returned %q, %v", value, err)
	}
}

func TestOneJSONLineRejectsMultipleLines(t *testing.T) {
	if _, err := oneJSONLine("{}\n{}"); err == nil {
		t.Fatal("oneJSONLine accepted multiple result lines")
	}
}

func TestRunRejectsNonObjectCommandBeforeKubernetesAccess(t *testing.T) {
	if _, err := run(t.Context(), "ignored", "ignored", "ignored", "[]", 0); err == nil {
		t.Fatal("run accepted an array as a command")
	}
}
