#!/usr/bin/env bash
# Generate secrets for Syntara development environment
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

# Returns 0 when password meets validate_password_complexity rules.
admin_password_meets_complexity() {
    printf '%s' "$1" |
        (cd "$PROJECT_ROOT" && uv run python -c '
import sys
from syntara.auth.passwords import validate_password_complexity

try:
    validate_password_complexity(sys.stdin.read())
except ValueError:
    raise SystemExit(1)
')
}

# Generate a bootstrap admin password that satisfies validate_password_complexity.
# openssl rand -base64 can miss a class (~0.1% of the time), which flakes CI when
# orchestrator-admin reset-password validates the secret.
generate_admin_password() {
    local password
    local attempt=0
    local max_attempts=100

    while ((attempt < max_attempts)); do
        password=$(openssl rand -base64 24 | tr -d '\n')
        if admin_password_meets_complexity "$password"; then
            echo -n "$password"
            return 0
        fi
        attempt=$((attempt + 1))
    done

    error "Failed to generate admin password meeting complexity requirements after ${max_attempts} attempts"
    return 1
}

# Generate the encryption key atomically so a failed openssl call cannot leave
# an empty file that later runs mistake for an existing key.
generate_encryption_key() {
    local temporary_path

    if ! temporary_path=$(mktemp "$SECRETS_DIR/.encryption-key.XXXXXX"); then
        error "Failed to create temporary encryption key file"
        return 1
    fi

    if ! openssl rand -hex 32 > "$temporary_path"; then
        rm -f "$temporary_path"
        error "Failed to generate encryption key"
        return 1
    fi

    if ! chmod 600 "$temporary_path" || ! mv -f "$temporary_path" "$SECRETS_DIR/encryption-key"; then
        rm -f "$temporary_path"
        error "Failed to install encryption key"
        return 1
    fi
}

# Match CredentialEncryptionSettings' required 32-byte hex format and reject
# its explicitly forbidden all-zero default without importing app settings.
encryption_key_is_valid() {
    local key

    [[ -s "$SECRETS_DIR/encryption-key" ]] || return 1
    key=$(cat "$SECRETS_DIR/encryption-key") || return 1
    [[ "$key" =~ ^[[:xdigit:]]{64}$ ]] || return 1
    [[ "$key" =~ ^0{64}$ ]] && return 1
    return 0
}

# Validate the candidate before atomically replacing the admin password file.
write_admin_password() {
    local temporary_path

    if ! temporary_path=$(mktemp "$SECRETS_DIR/.admin-password.XXXXXX"); then
        error "Failed to create temporary admin password file"
        return 1
    fi

    if [[ -n "${APP_ADMIN_PASSWORD:-}" ]]; then
        if ! admin_password_meets_complexity "$APP_ADMIN_PASSWORD"; then
            rm -f "$temporary_path"
            error "APP_ADMIN_PASSWORD does not meet complexity requirements"
            return 1
        fi
        printf '%s' "$APP_ADMIN_PASSWORD" > "$temporary_path"
    elif ! generate_admin_password > "$temporary_path"; then
        rm -f "$temporary_path"
        return 1
    fi

    if ! chmod 600 "$temporary_path" || ! mv -f "$temporary_path" "$SECRETS_DIR/admin-password"; then
        rm -f "$temporary_path"
        error "Failed to install admin password file"
        return 1
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
                echo "Generate JWT signing keys for Syntara development environment."
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

    # Password validation imports application settings, which require this file.
    # Create it before validating either a generated or configured password.
    if [[ "$force" != true ]] && encryption_key_is_valid; then
        info "Encryption key already exists, skipping (use --force to regenerate)"
    else
        if [[ -e "$SECRETS_DIR/encryption-key" ]] && [[ "$force" != true ]]; then
            info "Existing encryption key is invalid, replacing it"
        fi
        info "Generating encryption key..."
        generate_encryption_key
        info "  Encryption key: $SECRETS_DIR/encryption-key"
    fi

    # Generate admin password file
    if [[ -f "$SECRETS_DIR/admin-password" ]] && [[ "$force" != true ]]; then
        info "Admin password file already exists, skipping (use --force to regenerate)"
    else
        info "Generating admin password file..."
        write_admin_password
        if [[ -n "${APP_ADMIN_PASSWORD:-}" ]]; then
            info "  Using password from APP_ADMIN_PASSWORD env var"
        else
            info "  Generated random password"
        fi
        info "  Password file: $SECRETS_DIR/admin-password"
    fi

    # Prevent permissions issues once secrets are mounted to syntara containers
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
