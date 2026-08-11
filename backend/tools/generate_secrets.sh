#!/usr/bin/env bash
# Generate secrets for Nexus development environment
#
# This script generates:
# - ES256 (ECDSA P-256) key pairs for JWT signing (primary + backup)
# - Bootstrap admin password file
#
# Secrets are stored in .secrets/ directory and mounted to /run/secrets in containers.
#
# Usage:
#   ./tools/generate_secrets.sh         # Generate secrets if they don't exist
#   ./tools/generate_secrets.sh --force # Regenerate all secrets

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SECRETS_DIR="$PROJECT_ROOT/.secrets"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Check if openssl is available
check_dependencies() {
    if ! command -v openssl &> /dev/null; then
        error "openssl is required but not installed."
        exit 1
    fi
}

# Generate an ES256 (ECDSA P-256) key pair
generate_key_pair() {
    local key_name="$1"
    local private_key_path="$SECRETS_DIR/${key_name}.pem"
    local public_key_path="$SECRETS_DIR/${key_name}.pub"

    info "Generating $key_name key pair..."

    # Generate private key (ECDSA P-256)
    openssl ecparam -name prime256v1 -genkey -noout -out "$private_key_path"

    # Extract public key
    openssl ec -in "$private_key_path" -pubout -out "$public_key_path" 2>/dev/null

    # Set restrictive permissions
    chmod 600 "$private_key_path"
    chmod 644 "$public_key_path"

    info "  Private key: $private_key_path"
    info "  Public key:  $public_key_path"
}

# Main function
main() {
    local force=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force|-f)
                force=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [--force]"
                echo ""
                echo "Generate JWT signing keys for Nexus development environment."
                echo ""
                echo "Options:"
                echo "  --force, -f  Regenerate all keys even if they exist"
                echo "  --help, -h   Show this help message"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    check_dependencies

    # Create secrets directory if it doesn't exist
    if [[ ! -d "$SECRETS_DIR" ]]; then
        info "Creating secrets directory: $SECRETS_DIR"
        mkdir -p "$SECRETS_DIR"
        chmod 700 "$SECRETS_DIR"
    fi

    # Generate primary key
    if [[ -f "$SECRETS_DIR/jwt-primary.pem" ]] && [[ "$force" != true ]]; then
        info "Primary key already exists, skipping (use --force to regenerate)"
    else
        generate_key_pair "jwt-primary"
    fi

    # Generate backup key
    if [[ -f "$SECRETS_DIR/jwt-backup.pem" ]] && [[ "$force" != true ]]; then
        info "Backup key already exists, skipping (use --force to regenerate)"
    else
        generate_key_pair "jwt-backup"
    fi

    # Generate admin password file
    if [[ -f "$SECRETS_DIR/admin-password" ]] && [[ "$force" != true ]]; then
        info "Admin password file already exists, skipping (use --force to regenerate)"
    else
        info "Generating admin password file..."
        if [[ -n "${APP_ADMIN_PASSWORD:-}" ]]; then
            echo -n "$APP_ADMIN_PASSWORD" > "$SECRETS_DIR/admin-password"
            info "  Using password from APP_ADMIN_PASSWORD env var"
        else
            openssl rand -base64 24 > "$SECRETS_DIR/admin-password"
            info "  Generated random password"
        fi
        chmod 600 "$SECRETS_DIR/admin-password"
        info "  Password file: $SECRETS_DIR/admin-password"
    fi

    # Generate encryption key file
    if [[ -f "$SECRETS_DIR/encryption-key" ]] && [[ "$force" != true ]]; then
        info "Encryption key already exists, skipping (use --force to regenerate)"
    else
        info "Generating encryption key..."
        openssl rand -hex 32 > "$SECRETS_DIR/encryption-key"
        chmod 600 "$SECRETS_DIR/encryption-key"
        info "  Encryption key: $SECRETS_DIR/encryption-key"
    fi

    # Prevent permissions issues once secrets are mounted to nexus containers
    chmod -R +r "${SECRETS_DIR}"

    echo ""
    info "Secrets are ready in $SECRETS_DIR"
    info "Mount to containers via podman-compose or set environment variables:"
    info "  APP_JWT_PRIVATE_KEY_PATH=/run/secrets/jwt-primary.pem"
    info "  APP_JWT_BACKUP_KEYS='[{\"key_id\":\"orchestrator-backup\",\"key_path\":\"/run/secrets/jwt-backup.pem\"}]'"
    info "  APP_ADMIN_PASSWORD_PATH=/run/secrets/admin-password"
    info "  APP_SECRET_ENCRYPTION_KEY_PATH=/run/secrets/encryption-key"
    info ""
    info "Bootstrap admin password saved to: $SECRETS_DIR/admin-password"
}

main "$@"
