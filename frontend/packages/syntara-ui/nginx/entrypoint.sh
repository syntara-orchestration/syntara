#!/bin/bash
set -e

# When APP_API_URL is set, generate the API proxy config from the template.
# Without it the image serves static files only (production behavior).
if [ -n "${APP_API_URL}" ]; then
    # Validate URL format to prevent SSRF and nginx config injection.
    if [[ ! "${APP_API_URL}" =~ ^https?://[a-zA-Z0-9._-]+(:[0-9]+)?/?$ ]]; then
        echo "ERROR: APP_API_URL has invalid format: ${APP_API_URL}" >&2
        exit 1
    fi

    envsubst '${APP_API_URL}' \
        < /opt/app-root/etc/nginx/api-proxy.conf.template \
        > /opt/app-root/etc/nginx.default.d/api-proxy.conf
fi

# Validate nginx configuration before starting.
nginx -t

exec "$@"
