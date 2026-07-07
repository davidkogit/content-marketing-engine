#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Content Marketing Engine — One-Shot Deployment Script
#
# Idempotent: safe to run multiple times. Checks for existing resources before
# creating them. Skips steps that are already completed.
#
# Usage:
#   bash deploy/setup.sh
#   DOMAIN=example.com SUPER_ADMIN_EMAIL=admin@example.com bash deploy/setup.sh
#   bash deploy/setup.sh --help
###############################################################################

# ── Resolve paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/content-marketing-engine}"
APP_USER="content-engine"
APP_GROUP="content-engine"
PYTHON_BIN="${PYTHON_MINOR:-python3.11}"
NODE_MAJOR="${NODE_MAJOR:-22}"
CADDYFILE_SRC="$SCRIPT_DIR/Caddyfile"
# Use IP-friendly Caddyfile when no domain or IP-only mode is set
if [ "${USE_IP_ONLY:-false}" = "true" ] || [[ "${DOMAIN:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    log_info "Detected IP-only deployment — using HTTP (no TLS) Caddyfile."
    CADDYFILE_SRC="$SCRIPT_DIR/Caddyfile.ip"
fi
SERVICE_SRC="$SCRIPT_DIR/content-engine.service"
SERVICE_DST="/etc/systemd/system/content-engine.service"

# ── Terminal colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# ── Logging helpers ───────────────────────────────────────────────────────────
log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

die() {
    log_error "$*"
    exit 1
}

# ── Help ──────────────────────────────────────────────────────────────────────
show_help() {
    cat << 'HELP'
Content Marketing Engine — Production Deployment

Usage: bash deploy/setup.sh [OPTIONS]

Options:
  --help        Show this help message and exit
  --skip-venv   Skip Python virtual environment setup (reuse existing)
  --rebuild     Force rebuild frontend even if already built

Environment Variables (for automation / CI):
  DOMAIN                        Public domain name (e.g. example.com)
  SUPER_ADMIN_EMAIL             Initial super-admin account email
  APP_DIR                       Application root (default: /opt/content-marketing-engine)
  PYTHON_MINOR                  Python interpreter to use (default: python3.11)
  NODE_MAJOR                    Node.js major version for Nodesource setup (default: 18)

Interactive prompts are used when DOMAIN or SUPER_ADMIN_EMAIL are not set.

What this script does:
  1. Install system dependencies: python3.11, pip, Node.js 18+, Caddy
  2. Create a dedicated system user/group (content-engine)
  3. Set up the application directory tree under $APP_DIR
  4. Create a Python virtualenv and install backend requirements
  5. Build the React frontend with npm
  6. Copy and enable the systemd service unit
  7. Configure Caddy reverse-proxy (if Caddyfile exists)
  8. Seed default brand-rule templates if missing
  9. Write a .env file with domain and super-admin email
 10. Start services

HELP
    exit 0
}

# ── Parse flags ───────────────────────────────────────────────────────────────
SKIP_VENV=false
REBUILD=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help)    show_help ;;
        --skip-venv) SKIP_VENV=true; shift ;;
        --rebuild) REBUILD=true; shift ;;
        *)
            log_error "Unknown option: $1"
            echo "Run with --help for usage information."
            exit 1
            ;;
    esac
done

# ── Privilege guard ───────────────────────────────────────────────────────────
require_root() {
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root (try sudo)."
    fi
}

# ── OS detection ──────────────────────────────────────────────────────────────
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID}"
        OS_VERSION="${VERSION_ID}"
    else
        die "Cannot detect OS — /etc/os-release not found. Only Ubuntu/Debian are supported."
    fi

    case "$OS_ID" in
        ubuntu|debian) log_info "Detected $OS_ID $OS_VERSION" ;;
        *) die "Unsupported OS: $OS_ID. This script supports Ubuntu and Debian." ;;
    esac
}

# ── System dependencies ───────────────────────────────────────────────────────
install_system_deps() {
    log_info "Installing system dependencies …"

    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq

    # ── Python 3.11 ─
    if ! command -v "$PYTHON_BIN" &>/dev/null; then
        log_info "Installing $PYTHON_BIN …"
        case "$OS_ID" in
            ubuntu)
                apt-get install -y -qq software-properties-common
                add-apt-repository -y ppa:deadsnakes/ppa
                apt-get update -qq
                apt-get install -y -qq "$PYTHON_BIN" "$PYTHON_BIN-venv" "$PYTHON_BIN-dev"
                ;;
            debian)
                # Debian bookworm+ ships 3.11 natively
                apt-get install -y -qq "$PYTHON_BIN" "$PYTHON_BIN-venv" "$PYTHON_BIN-dev" || \
                    die "Python 3.11 not available. Upgrade to Debian 12+ or use Ubuntu."
                ;;
        esac
    else
        log_info "$PYTHON_BIN already installed — skipping."
    fi

    # ── pip ─ (ensure pip is available inside venv later)
    if ! command -v pip3 &>/dev/null; then
        apt-get install -y -qq python3-pip
    fi

    # ── Node.js ─
    if ! command -v node &>/dev/null; then
        log_info "Installing Node.js $NODE_MAJOR.x …"
        curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
        apt-get install -y -qq nodejs
    else
        log_info "Node.js $(node --version) already installed — skipping."
    fi

    # ── Caddy ─
    if ! command -v caddy &>/dev/null; then
        log_info "Installing Caddy …"
        apt-get install -y -qq debian-keyring debian-archive-keyring
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
            | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
            | tee /etc/apt/sources.list.d/caddy-stable.list
        apt-get update -qq
        apt-get install -y -qq caddy
    else
        log_info "Caddy $(caddy version | head -1) already installed — skipping."
    fi

    # ── Misc tools used by backend ──
    apt-get install -y -qq curl wget build-essential

    log_info "System dependencies installed."
}

# ── System user ───────────────────────────────────────────────────────────────
create_app_user() {
    if id "$APP_USER" &>/dev/null; then
        log_info "User '$APP_USER' already exists — skipping."
    else
        log_info "Creating system user '$APP_USER' …"
        useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
    fi
}

# ── Directory tree ────────────────────────────────────────────────────────────
setup_directories() {
    log_info "Setting up application directories under $APP_DIR …"

    # Create dirs only if they don't exist (idempotent)
    mkdir -p "$APP_DIR/backend/data/rules"
    mkdir -p "$APP_DIR/backend/data/brand-rules"
    mkdir -p "$APP_DIR/frontend"

    # Deploy backend source
    if [ ! -f "$APP_DIR/backend/requirements.txt" ]; then
        log_info "Copying backend source …"
        rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' \
            "$PROJECT_DIR/backend/" "$APP_DIR/backend/"
    else
        log_info "Backend source already present — skipping."
    fi

    # Deploy frontend source
    if [ ! -f "$APP_DIR/frontend/package.json" ]; then
        log_info "Copying frontend source …"
        rsync -a --exclude='node_modules' --exclude='dist' \
            "$PROJECT_DIR/frontend/" "$APP_DIR/frontend/"
    else
        log_info "Frontend source already present — skipping."
    fi

    chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
    chmod 755 "$APP_DIR/backend/data"
    chmod 755 "$APP_DIR/backend/data/rules"
    chmod 755 "$APP_DIR/backend/data/brand-rules"

    log_info "Directories set up."
}

# ── Python virtual environment ────────────────────────────────────────────────
setup_venv() {
    if $SKIP_VENV; then
        log_info "Skipping venv setup (--skip-venv)."
        return
    fi

    local venv_dir="$APP_DIR/backend/.venv"

    if [ -f "$venv_dir/bin/python" ]; then
        log_info "Virtualenv already exists at $venv_dir — skipping."
        log_info "Use --skip-venv to bypass this warning in the future."
        return
    fi

    log_info "Creating Python virtual environment …"
    "$PYTHON_BIN" -m venv "$venv_dir" || die "Failed to create virtualenv."

    log_info "Upgrading pip and setuptools …"
    "$venv_dir/bin/pip" install --upgrade pip setuptools wheel

    if [ -f "$APP_DIR/backend/requirements.txt" ]; then
        log_info "Installing Python requirements …"
        "$venv_dir/bin/pip" install -r "$APP_DIR/backend/requirements.txt"
    else
        log_warn "No requirements.txt found — installing core deps manually."
        "$venv_dir/bin/pip" install fastapi uvicorn[standard] bcrypt pyjwt httpx pdfplumber
    fi

    log_info "Python environment ready."
}

# ── Frontend build ────────────────────────────────────────────────────────────
build_frontend() {
    local frontend_dir="$APP_DIR/frontend"

    if [ ! -f "$frontend_dir/package.json" ]; then
        log_warn "No package.json found in frontend — skipping frontend build."
        return
    fi

    if $REBUILD; then
        log_info "Forcing frontend rebuild (--rebuild)."
        rm -rf "$frontend_dir/node_modules" "$frontend_dir/dist"
    fi

    if [ -d "$frontend_dir/dist" ]; then
        log_info "Frontend already built at $frontend_dir/dist — skipping."
        log_info "Use --rebuild to force a rebuild."
        return
    fi

    log_info "Installing frontend dependencies (npm ci) …"
    (cd "$frontend_dir" && npm ci --production=false)

    log_info "Building frontend (npm run build) …"
    (cd "$frontend_dir" && npm run build)

    log_info "Frontend built."
}

# ── Default brand rules ───────────────────────────────────────────────────────
seed_brand_rules() {
    local rules_dir="$APP_DIR/backend/data/brand-rules"

    mkdir -p "$rules_dir"

    # Brand Voice
    if [ ! -f "$rules_dir/brand-voice.md" ]; then
        cat > "$rules_dir/brand-voice.md" << 'BRANDVOICE'
# Brand Voice Guidelines

## Tone
- Professional yet approachable
- Confident but not arrogant
- Educational, not salesy

## Language
- Write at a 10th-grade reading level
- Use active voice
- Keep sentences under 25 words
- Avoid jargon unless targeting a technical audience

## Terminology
- ALWAYS: use product name as listed in the SKU spec
- NEVER: claim "best," "guaranteed," or "risk-free" unless certified
BRANDVOICE
        log_info "Created default brand-voice.md."
    else
        log_info "brand-voice.md exists — skipping."
    fi

    # Compliance Rules
    if [ ! -f "$rules_dir/compliance.md" ]; then
        cat > "$rules_dir/compliance.md" << 'COMPLIANCE'
# Compliance Rules

## Claim Verification
- Every claim MUST cite a source document
- No superlatives without quantitative evidence
- Health claims require clinical-study citation

## Regulatory
- Do not make therapeutic claims unless FDA/EMA approved
- Disclose material connections (affiliate links, sponsorships)
- Respect trademark symbols (®, ™, ©)
COMPLIANCE
        log_info "Created default compliance.md."
    else
        log_info "compliance.md exists — skipping."
    fi

    # Content Structure
    if [ ! -f "$rules_dir/content-structure.md" ]; then
        cat > "$rules_dir/content-structure.md" << 'STRUCTURE'
# Content Structure Rules

## Format
- Every piece includes: headline, body, call-to-action
- Headline: ≤ 70 characters
- Body: broken into scannable sections with subheadings

## Required Sections
1. Problem statement (1-2 sentences)
2. Solution overview
3. Key features / benefits (bulleted)
4. Evidence / social proof
5. Call to action

## Prohibited
- Walls of text (paragraphs > 5 lines)
- Missing CTA
- Clickbait headlines
STRUCTURE
        log_info "Created default content-structure.md."
    else
        log_info "content-structure.md exists — skipping."
    fi

    chown -R "$APP_USER:$APP_GROUP" "$rules_dir"
}

# ── Environment file ─────────────────────────────────────────────────────────
write_env_file() {
    local env_file="$APP_DIR/.env"

    if [ -f "$env_file" ]; then
        log_info ".env file already exists — skipping."
        log_info "Remove $env_file manually if you need to regenerate."
        return
    fi

    log_info "Generating .env file …"

    # Domain prompt / env var
    local domain="${DOMAIN:-}"
    if [ -z "$domain" ]; then
        # Try alternate env var name
        domain="${CONTENT_ENGINE_DOMAIN:-}"
    fi
    if [ -z "$domain" ]; then
        read -rp "Public domain name (e.g. example.com): " domain
    fi
    if [ -z "$domain" ]; then
        die "Domain name is required. Set DOMAIN env var or provide it interactively."
    fi

    # Super admin email prompt / env var
    local super_admin_email="${SUPER_ADMIN_EMAIL:-}"
    if [ -z "$super_admin_email" ]; then
        read -rp "Initial super-admin email: " super_admin_email
    fi
    if [ -z "$super_admin_email" ]; then
        die "Super-admin email is required. Set SUPER_ADMIN_EMAIL env var or provide it interactively."
    fi

    # Generate a secure secret key
    local secret_key
    secret_key="$($PYTHON_BIN -c "import secrets; print(secrets.token_urlsafe(64))")"

    cat > "$env_file" << ENVEOF
# Content Marketing Engine — Environment Configuration
# Generated: $(date --iso-8601=seconds)

DOMAIN=$domain
SUPER_ADMIN_EMAIL=$super_admin_email
SECRET_KEY=$secret_key

# Database (SQLite — file path relative to backend/)
DATABASE_URL=sqlite:///./data/products.db

# CORS (comma-separated origins allowed)
CORS_ORIGINS=https://$domain

# LLM Provider (to be configured by Super Admin via UI)
LLM_PROVIDER=openai
LLM_MODEL=gpt-4
LLM_API_KEY=

# Logging
LOG_LEVEL=info
ENVEOF

    chown "$APP_USER:$APP_GROUP" "$env_file"
    chmod 600 "$env_file"
    log_info ".env file written to $env_file (permissions: 600)."
}

# ── systemd service ───────────────────────────────────────────────────────────
setup_systemd() {
    if [ ! -f "$SERVICE_SRC" ]; then
        log_warn "Systemd unit file not found at $SERVICE_SRC — skipping."
        return
    fi

    cp "$SERVICE_SRC" "$SERVICE_DST"
    chmod 644 "$SERVICE_DST"
    systemctl daemon-reload
    log_info "Systemd unit installed to $SERVICE_DST."
}

# ── Caddy configuration ───────────────────────────────────────────────────────
setup_caddy() {
    if [ ! -f "$CADDYFILE_SRC" ]; then
        log_warn "Caddyfile not found at $CADDYFILE_SRC — skipping reverse-proxy setup."
        return
    fi

    cp "$CADDYFILE_SRC" /etc/caddy/Caddyfile
    chmod 644 /etc/caddy/Caddyfile
    log_info "Caddyfile installed to /etc/caddy/Caddyfile."
}

# ── Start services ────────────────────────────────────────────────────────────
start_services() {
    log_info "Enabling and starting services …"

    systemctl enable content-engine.service
    systemctl restart content-engine.service

    if systemctl is-enabled caddy &>/dev/null; then
        systemctl restart caddy
    else
        systemctl enable --now caddy
    fi

    # Verify
    sleep 2
    if systemctl is-active --quiet content-engine.service; then
        log_info "content-engine.service is running."
    else
        log_warn "content-engine.service may not have started. Check: journalctl -u content-engine"
    fi

    if systemctl is-active --quiet caddy; then
        log_info "Caddy is running."
    else
        log_warn "Caddy may not have started. Check: journalctl -u caddy"
    fi
}

# ── Summary ───────────────────────────────────────────────────────────────────
print_summary() {
    local domain
    domain="$(grep '^DOMAIN=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "unknown")"

    echo ""
    echo -e "${BOLD}============================================${NC}"
    echo -e "${BOLD}  Content Marketing Engine — Setup Complete${NC}"
    echo -e "${BOLD}============================================${NC}"
    echo ""
    echo -e "  App root:     ${GREEN}$APP_DIR${NC}"
    echo -e "  Backend API:  ${GREEN}https://$domain/api/${NC}"
    echo -e "  API Docs:     ${GREEN}https://$domain/docs${NC}"
    echo -e "  Dashboard:    ${GREEN}https://$domain/${NC}"
    echo -e "  Health check: ${GREEN}https://$domain/health${NC}"
    echo ""
    echo -e "  View logs:    ${YELLOW}journalctl -u content-engine -f${NC}"
    echo -e "  View status:  ${YELLOW}systemctl status content-engine${NC}"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}Content Marketing Engine — Deployment Setup${NC}"
    echo ""

    require_root
    detect_os
    install_system_deps
    create_app_user
    setup_directories
    setup_venv
    build_frontend
    seed_brand_rules
    write_env_file
    setup_systemd
    setup_caddy
    start_services
    print_summary
}

main "$@"
