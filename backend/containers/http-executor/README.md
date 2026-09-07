# Syntara HTTP executor

This image reads one JSON command per stdin line and writes one JSON result per
stdout line. It never follows redirects and does not use proxy environment
variables.

```console
printf '%s\n' '{"method":"GET","url":"https://example.com"}' |
  podman run --rm -i quay.io/ORGANIZATION/syntara-http-executor:VERSION
```

Supported command fields are `method`, `url`, `headers`, `query_params`,
`body`, `authentication`, and `timeout_seconds`. Authentication has `type`
(`basic`, `bearer`, `api_key`, or `oauth2`) and inline `credentials` fields.

The executor rejects loopback, private, link-local, reserved, and other
non-public resolved IP addresses. OpenShift egress policy must still enforce
this boundary because DNS may change after validation.
