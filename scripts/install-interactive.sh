#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="/opt/SignalKiosk"
TMP_DIR=""

DEFAULT_REPO_URL="https://github.com/essendyx/SignalKiosk.git"
DEFAULT_ADMIN_PORT="8080"
DEFAULT_PLAYBACK_PORT="8081"
DEFAULT_TZ="Europe/Berlin"
DEFAULT_ADMIN_USER="admin"
DEFAULT_ADMIN_PASS="admin"

log() { printf "\n[%s] %s\n" "$1" "$2"; }
info() { printf "[INFO] %s\n" "$1"; }
warn() { printf "[WARN] %s\n" "$1"; }
die() { printf "[ERROR] %s\n" "$1" >&2; exit 1; }

cleanup() {
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}

on_error() {
  local line="$1"
  local cmd="$2"
  printf "\n[ERROR] Installation aborted at line %s: %s\n" "${line}" "${cmd}" >&2
}

trap cleanup EXIT
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

ensure_root() {
  [[ "${EUID}" -eq 0 ]] || die "Please run as root: sudo bash scripts/install-interactive.sh"
}

ensure_ubuntu() {
  [[ -f /etc/os-release ]] || die "/etc/os-release not found"
  # shellcheck source=/dev/null
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || die "This installer currently supports Ubuntu only"
}

prompt_default() {
  local prompt="$1"
  local default="$2"
  local value=""
  read -r -p "${prompt} [${default}]: " value
  if [[ -z "${value}" ]]; then
    printf "%s" "${default}"
  else
    printf "%s" "${value}"
  fi
}

is_valid_username() {
  local u="$1"
  [[ "${u}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]
}

is_valid_port() {
  local p="$1"
  [[ "${p}" =~ ^[0-9]+$ ]] || return 1
  (( p >= 1 && p <= 65535 ))
}

port_in_use() {
  local p="$1"
  ss -ltn "( sport = :${p} )" | tail -n +2 | grep -q .
}

upsert_env() {
  local key="$1"
  local value="$2"
  local file="$3"

  if grep -q "^${key}=" "${file}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${file}"
  else
    printf "%s=%s\n" "${key}" "${value}" >> "${file}"
  fi
}

generate_fernet_key() {
  python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
}

generate_hex_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
}

configure_desktop_autologin() {
  local user="$1"
  log "DESKTOP" "Installing desktop packages and enabling autologin"
  apt-get update
  echo "lightdm shared/default-x-display-manager select lightdm" | debconf-set-selections
  DEBIAN_FRONTEND=noninteractive apt-get install -y xfce4 xfce4-goodies lightdm
  dpkg-reconfigure -f noninteractive lightdm || true
  systemctl set-default graphical.target
  systemctl enable lightdm
  mkdir -p /etc/lightdm/lightdm.conf.d
  cat > /etc/lightdm/lightdm.conf.d/50-signalkiosk-autologin.conf <<EOF
[Seat:*]
autologin-user=${user}
autologin-user-timeout=0
user-session=xfce
EOF
}

configure_kiosk_hardening() {
  local user="$1"
  log "HARDENING" "Configuring kiosk display no-blank settings"

  mkdir -p /etc/xdg/autostart
  cat > /etc/xdg/autostart/signalkiosk-display-power.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=SignalKiosk Display Power
Exec=sh -c "xset s off -dpms s noblank"
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF

  local user_home
  user_home="$(eval echo "~${user}")"
  mkdir -p "${user_home}/.config/autostart"
  cat > "${user_home}/.config/autostart/signalkiosk-nosleep.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=SignalKiosk NoSleep
Exec=sh -c "xset s off -dpms s noblank; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -n -t bool -s false; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/blank-on-ac -n -t int -s 0; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/inactivity-on-ac -n -t int -s 14"
X-GNOME-Autostart-enabled=true
EOF
  chown -R "${user}:${user}" "${user_home}/.config"
}

configure_disable_autosuspend() {
  log "POWER" "Disabling autosuspend and sleep targets"

  mkdir -p /etc/systemd/logind.conf.d
  cat > /etc/systemd/logind.conf.d/50-signalkiosk.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
IdleActionSec=0
EOF

  mkdir -p /etc/systemd/sleep.conf.d
  cat > /etc/systemd/sleep.conf.d/50-signalkiosk.conf <<'EOF'
[Sleep]
AllowSuspend=no
AllowHibernation=no
AllowHybridSleep=no
AllowSuspendThenHibernate=no
EOF

  systemctl restart systemd-logind
  systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
  systemctl disable --now light-locker 2>/dev/null || true
  apt-get -y purge light-locker 'xscreensaver*' >/dev/null 2>&1 || true
}

apply_xfce_power_settings() {
  local user="$1"
  log "POWER" "Applying XFCE power settings for kiosk user"
  sudo -u "${user}" sh -lc 'if command -v xfconf-query >/dev/null 2>&1; then xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/power-button-action -n -t int -s 0; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/sleep-button-action -n -t int -s 0; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/hibernate-button-action -n -t int -s 0; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/inactivity-on-ac -n -t int -s 14; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -n -t bool -s false; fi'
}

write_post_reboot_verify_script() {
  cat > "${PROJECT_DIR}/scripts/post-reboot-verify.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

echo "DISPLAY: ${DISPLAY:-<empty>}"
systemctl is-active signalkiosk-cdp-runner.service
journalctl -u signalkiosk-cdp-runner.service -n 50 --no-pager
systemctl is-active signalkiosk-host-control.service
echo "Sleep target states:"
systemctl status sleep.target suspend.target hibernate.target hybrid-sleep.target --no-pager | sed -n '1,25p'
EOF
  chmod +x "${PROJECT_DIR}/scripts/post-reboot-verify.sh"
}

validate_fernet_key() {
  local key="$1"
  KEY_TO_CHECK="${key}" python3 - <<'PY'
import base64
import os
import sys

key = os.environ.get("KEY_TO_CHECK", "")
try:
    raw = base64.urlsafe_b64decode(key.encode())
except Exception:
    sys.exit(1)
if len(raw) != 32:
    sys.exit(1)
PY
}

select_install_mode() {
  local choice=""
  printf "\nInstall mode:\n"
  printf "  1) Release tag (recommended)\n"
  printf "  2) Local working copy\n"

  while true; do
    read -r -p "Choose mode [1]: " choice
    choice="${choice:-1}"
    case "${choice}" in
      1) printf "%s" "release"; return ;;
      2) printf "%s" "local"; return ;;
      *) warn "Please choose 1 or 2." ;;
    esac
  done
}

select_tag() {
  local repo_url="$1"
  local -a tags=()
  local line=""
  local tag=""
  local selection=""

  info "Fetching tags from ${repo_url}..."
  while IFS= read -r line; do
    tag="${line##refs/tags/}"
    tag="${tag%%^{}*}"
    [[ -n "${tag}" ]] && tags+=("${tag}")
  done < <(git ls-remote --tags --refs "${repo_url}")

  (( ${#tags[@]} > 0 )) || die "No tags found in remote repository"

  IFS=$'\n' tags=($(printf "%s\n" "${tags[@]}" | sort -Vr))
  unset IFS

  printf "\nAvailable tags (latest first):\n"
  local max_show=30
  local count=${#tags[@]}
  local i
  for ((i=0; i < count && i < max_show; i++)); do
    printf "  %2d) %s\n" "$((i+1))" "${tags[$i]}"
  done
  if (( count > max_show )); then
    printf "  ... (%d more tags not shown)\n" "$((count - max_show))"
  fi

  while true; do
    read -r -p "Choose tag number or enter tag name [1]: " selection
    selection="${selection:-1}"
    if [[ "${selection}" =~ ^[0-9]+$ ]]; then
      if (( selection >= 1 && selection <= count )); then
        printf "%s" "${tags[$((selection-1))]}"
        return
      fi
      warn "Invalid number. Please choose between 1 and ${count}."
      continue
    fi

    for tag in "${tags[@]}"; do
      if [[ "${tag}" == "${selection}" ]]; then
        printf "%s" "${tag}"
        return
      fi
    done
    warn "Tag not found: ${selection}"
  done
}

ensure_user_exists() {
  local user="$1"
  if id -u "${user}" >/dev/null 2>&1; then
    info "User '${user}' already exists."
    return
  fi

  log "USER" "Creating user '${user}'"
  adduser --gecos "" "${user}"
  usermod -aG sudo "${user}"
}

main() {
  ensure_root
  ensure_ubuntu
  require_cmd git
  require_cmd python3
  require_cmd curl
  require_cmd ss
  require_cmd sed
  require_cmd grep
  require_cmd awk
  require_cmd find

  log "PRECHECK" "Basic environment checks"
  if ! systemctl >/dev/null 2>&1; then
    die "systemd/systemctl not available"
  fi

  local install_mode
  install_mode="$(select_install_mode)"

  local repo_url="${DEFAULT_REPO_URL}"
  local selected_tag=""
  local source_dir="${REPO_ROOT}"

  if [[ "${install_mode}" == "release" ]]; then
    local detected_remote=""
    detected_remote="$(git -C "${REPO_ROOT}" config --get remote.origin.url || true)"
    if [[ -n "${detected_remote}" ]]; then
      repo_url="${detected_remote}"
    fi

    selected_tag="$(select_tag "${repo_url}")"
    info "Selected tag: ${selected_tag}"
  fi

  log "CONFIG" "Interactive configuration"

  local target_user
  while true; do
    target_user="$(prompt_default "Linux kiosk username" "signalkiosk")"
    if is_valid_username "${target_user}"; then
      break
    fi
    warn "Invalid username format. Use lowercase letters, digits, _ or -."
  done

  local admin_port playback_port tz_value
  while true; do
    admin_port="$(prompt_default "Admin port" "${DEFAULT_ADMIN_PORT}")"
    is_valid_port "${admin_port}" || { warn "Invalid admin port"; continue; }
    if port_in_use "${admin_port}"; then
      warn "Admin port ${admin_port} is already in use"
      continue
    fi
    break
  done

  while true; do
    playback_port="$(prompt_default "Playback/API port" "${DEFAULT_PLAYBACK_PORT}")"
    is_valid_port "${playback_port}" || { warn "Invalid playback port"; continue; }
    if [[ "${playback_port}" == "${admin_port}" ]]; then
      warn "Playback port must differ from admin port"
      continue
    fi
    if port_in_use "${playback_port}"; then
      warn "Playback port ${playback_port} is already in use"
      continue
    fi
    break
  done

  tz_value="$(prompt_default "Timezone (TZ)" "${DEFAULT_TZ}")"
  local admin_username admin_password
  admin_username="$(prompt_default "Initial admin username" "${DEFAULT_ADMIN_USER}")"
  admin_password="$(prompt_default "Initial admin password" "${DEFAULT_ADMIN_PASS}")"

  printf "\nSummary:\n"
  printf "  Mode: %s\n" "${install_mode}"
  if [[ "${install_mode}" == "release" ]]; then
    printf "  Repository: %s\n" "${repo_url}"
    printf "  Tag: %s\n" "${selected_tag}"
  fi
  printf "  User: %s\n" "${target_user}"
  printf "  ADMIN_PORT: %s\n" "${admin_port}"
  printf "  PLAYBACK_PORT: %s\n" "${playback_port}"
  printf "  TZ: %s\n" "${tz_value}"
  printf "  DEFAULT_ADMIN_USERNAME: %s\n" "${admin_username}"

  local proceed
  read -r -p "Proceed with installation? [y/N]: " proceed
  [[ "${proceed}" =~ ^[Yy]$ ]] || die "Cancelled by user"

  ensure_user_exists "${target_user}"

  if [[ "${install_mode}" == "release" ]]; then
    log "SOURCE" "Cloning selected release tag"
    TMP_DIR="$(mktemp -d -t signalkiosk-install-XXXXXX)"
    git clone --depth 1 --branch "${selected_tag}" "${repo_url}" "${TMP_DIR}/src"
    source_dir="${TMP_DIR}/src"
  else
    log "SOURCE" "Using local working copy"
  fi

  log "DEPLOY" "Preparing ${PROJECT_DIR}"
  mkdir -p "${PROJECT_DIR}"
  local env_backup_tmp=""
  if [[ -f "${PROJECT_DIR}/.env" ]]; then
    env_backup_tmp="$(mktemp -t signalkiosk-env-XXXXXX)"
    cp "${PROJECT_DIR}/.env" "${env_backup_tmp}"
  fi
  find "${PROJECT_DIR}" -mindepth 1 -maxdepth 1 ! -name '.env' ! -name '.env.bak.*' -exec rm -rf {} +
  cp -a "${source_dir}/." "${PROJECT_DIR}/"
  rm -rf "${PROJECT_DIR}/.git"
  if [[ -n "${env_backup_tmp}" && -f "${env_backup_tmp}" ]]; then
    cp "${env_backup_tmp}" "${PROJECT_DIR}/.env"
    rm -f "${env_backup_tmp}"
  fi

  cd "${PROJECT_DIR}"
  [[ -f .env ]] || cp .env.example .env
  cp .env ".env.bak.$(date +%Y%m%d%H%M%S)"

  local fernet_key host_token app_secret
  fernet_key="$(generate_fernet_key)"
  validate_fernet_key "${fernet_key}" || die "Generated Fernet key is invalid"
  host_token="$(generate_hex_secret)"
  app_secret="$(generate_hex_secret)"

  upsert_env "SECRET_ENCRYPTION_KEY" "${fernet_key}" .env
  upsert_env "HOST_CONTROL_TOKEN" "${host_token}" .env
  upsert_env "APP_SECRET_KEY" "${app_secret}" .env
  upsert_env "ADMIN_PORT" "${admin_port}" .env
  upsert_env "PLAYBACK_PORT" "${playback_port}" .env
  upsert_env "TZ" "${tz_value}" .env
  upsert_env "DEFAULT_ADMIN_USERNAME" "${admin_username}" .env
  upsert_env "DEFAULT_ADMIN_PASSWORD" "${admin_password}" .env
  upsert_env "HOST_CONTROL_URL" "http://127.0.0.1:9510" .env

  log "INSTALL" "Running base setup script"
  bash "${PROJECT_DIR}/scripts/setup-ubuntu-kiosk.sh"

  log "SERVICE" "Applying kiosk user to runner service"
  local uid_value
  uid_value="$(id -u "${target_user}")"
  mkdir -p /etc/systemd/system/signalkiosk-cdp-runner.service.d
  cat > /etc/systemd/system/signalkiosk-cdp-runner.service.d/10-user.conf <<EOF
[Service]
User=${target_user}
Group=${target_user}
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/${uid_value}
Environment=XAUTHORITY=/home/${target_user}/.Xauthority
EOF

  mkdir -p /var/lib/signalkiosk/chrome-profile
  chown -R "${target_user}:${target_user}" /var/lib/signalkiosk
  chmod -R u+rwX /var/lib/signalkiosk

  systemctl daemon-reload
  systemctl restart signalkiosk-cdp-runner.service
  systemctl restart signalkiosk-host-control.service

  configure_desktop_autologin "${target_user}"
  configure_kiosk_hardening "${target_user}"
  configure_disable_autosuspend
  apply_xfce_power_settings "${target_user}"
  write_post_reboot_verify_script

  log "VERIFY" "Running post-install checks"
  docker compose -f "${PROJECT_DIR}/docker-compose.yml" ps
  systemctl is-active --quiet signalkiosk-cdp-runner.service || die "Runner service is not active"
  systemctl is-active --quiet signalkiosk-host-control.service || die "Host control service is not active"
  curl -fsS "http://127.0.0.1:${playback_port}/health" >/dev/null || warn "Backend health endpoint not reachable yet"
  curl -fsS "http://127.0.0.1:${admin_port}" >/dev/null || warn "Admin UI not reachable yet"

  log "DONE" "Installation completed"
  printf "Admin UI: http://<server-ip>:%s\n" "${admin_port}"
  printf "Backend/API: http://<server-ip>:%s\n" "${playback_port}"
  printf "Post-reboot verify: sudo bash %s/scripts/post-reboot-verify.sh\n" "${PROJECT_DIR}"
  printf "Runner logs: journalctl -u signalkiosk-cdp-runner.service -f\n"
  printf "Host control logs: journalctl -u signalkiosk-host-control.service -f\n"

  local reboot_now
  read -r -p "Reboot now? [y/N]: " reboot_now
  if [[ "${reboot_now}" =~ ^[Yy]$ ]]; then
    reboot
  fi
}

main "$@"
