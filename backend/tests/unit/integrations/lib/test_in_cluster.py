"""Tests for integrations/lib/in_cluster.py — the in-cluster Kubernetes API helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from syntara.integrations.lib import in_cluster
from syntara.integrations.lib.in_cluster import (
    in_cluster_kubernetes_api_hosts,
    is_in_cluster_kubernetes_api_url,
    service_account_ca_certificate,
)


class TestInClusterKubernetesApiHosts:
    """Tests for in_cluster_kubernetes_api_hosts()."""

    def test_empty_outside_a_cluster(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No host is auto-allowed when the kubelet's in-cluster signal is absent."""
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        assert in_cluster_kubernetes_api_hosts() == frozenset()

    def test_api_hostnames_inside_a_cluster(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The API Service hostnames are returned when the signal is present."""
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
        assert in_cluster_kubernetes_api_hosts() == in_cluster.IN_CLUSTER_KUBERNETES_API_HOSTS
        assert "kubernetes.default.svc" in in_cluster_kubernetes_api_hosts()


class TestIsInClusterKubernetesApiUrl:
    """Tests for is_in_cluster_kubernetes_api_url()."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://kubernetes.default.svc",
            "https://kubernetes.default.svc:443",
            "https://kubernetes.default",
            "https://Kubernetes.Default.Svc",
        ],
    )
    def test_api_spellings_match(self, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Every spelling of the API Service matches, case-insensitively, port ignored."""
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
        assert is_in_cluster_kubernetes_api_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://myao-backend.default.svc",
            "https://kubernetes.default.svc.example.com",
            "https://evil-kubernetes.default.svc",
            "https://kubernetes",
            # The FQDN is excluded on purpose: the SSRF engine rejects every
            # ".svc.cluster.local" hostname unconditionally, so it can never pass.
            "https://kubernetes.default.svc.cluster.local",
        ],
    )
    def test_other_hosts_do_not_match(self, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unrelated in-cluster services, suffix lookalikes, and the bare name never match."""
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
        assert is_in_cluster_kubernetes_api_url(url) is False

    def test_no_match_outside_a_cluster(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even the API Service URL does not match when not running in a cluster."""
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        assert is_in_cluster_kubernetes_api_url("https://kubernetes.default.svc") is False


class TestServiceAccountCaCertificate:
    """Tests for service_account_ca_certificate()."""

    def test_returns_bundle_contents(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """The mounted CA bundle is returned when present."""
        ca = tmp_path / "ca.crt"
        ca.write_text("-----BEGIN CERTIFICATE-----")
        monkeypatch.setattr(in_cluster, "_SERVICE_ACCOUNT_CA", ca)
        assert service_account_ca_certificate() == "-----BEGIN CERTIFICATE-----"

    def test_returns_none_when_absent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """A missing bundle yields None so callers fall back to the system trust store."""
        monkeypatch.setattr(in_cluster, "_SERVICE_ACCOUNT_CA", tmp_path / "absent.crt")
        assert service_account_ca_certificate() is None
