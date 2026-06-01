#!/usr/bin/env bash
#
# Virtual Monitor Installer/Uninstaller
# Creates a virtual display via kernel EDID emulation.
#
# Usage:
#   sudo bash setup-virtual-monitor.sh install          # 1920x1080@60
#   sudo bash setup-virtual-monitor.sh install -r 2560x1440 -R 75
#   sudo bash setup-virtual-monitor.sh uninstall
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

MODE=""
CONNECTOR=""
RES_W=1920
RES_H=1080
REFRESH=60

EDID_DIR="/usr/lib/firmware/edid"
GRUB_FILE="/etc/default/grub"
GRUB_BAK="${GRUB_FILE}.bak.virtual-monitor"

# ---- helpers ----------------------------------------------------------
die()   { echo -e "\e[31mERROR: $*\e[0m" >&2; exit 1; }
info()  { echo -e "\e[36m$*\e[0m"; }
ok()    { echo -e "\e[32m==> $*\e[0m"; }

check_root() { [[ $EUID -eq 0 ]] || die "Please run as root (sudo $0)"; }

detect_connector() {
    local card base
    for card in /sys/class/drm/card0-HDMI-*/; do
        base="${card%/}"; base="${base##*/card0-}"
        [[ -n "$base" ]] && { CONNECTOR="$base"; return 0; }
    done
    for card in /sys/class/drm/card0-DP-*/; do
        base="${card%/}"; base="${base##*/card0-}"
        [[ -n "$base" ]] && { CONNECTOR="$base"; return 0; }
    done
    die "No HDMI or DP connector found on card0"
}

# ---- EDID generation --------------------------------------------------
generate_edid() {
    info "Generating ${RES_W}x${RES_H}@${REFRESH} EDID..."
    mkdir -p "$EDID_DIR"

    local out="${EDID_DIR}/${RES_W}x${RES_H}.bin"
    python3 "${SCRIPT_DIR}/generate-edid.py" \
        -w "$RES_W" -H "$RES_H" -r "$REFRESH" "$out"
    ok "EDID written to ${out}"
    EDID_FILE="$out"
}

# ---- GRUB -------------------------------------------------------------
install_grub() {
    local edid_name="${RES_W}x${RES_H}.bin"
    local param="drm.edid_firmware=${CONNECTOR}:edid/${edid_name} video=${CONNECTOR}:${RES_W}x${RES_H}@${REFRESH}e"
    local marker="# virtual-monitor: ${CONNECTOR} ${RES_W}x${RES_H}@${REFRESH}"

    if grep -qF "$marker" "$GRUB_FILE" 2>/dev/null; then
        info "Virtual monitor config already present in GRUB, skipping"
        return
    fi

    cp "$GRUB_FILE" "$GRUB_BAK"
    ok "Backed up ${GRUB_FILE} -> ${GRUB_BAK}"

    local old old_line new_line
    old_line=$(grep '^GRUB_CMDLINE_LINUX=' "$GRUB_FILE" | head -1)
    old=$(echo "$old_line" | sed 's/^GRUB_CMDLINE_LINUX="\(.*\)"$/\1/')
    if [[ -z "$old" ]]; then
        new_line="GRUB_CMDLINE_LINUX=\"${param}\""
    else
        new_line="GRUB_CMDLINE_LINUX=\"${old} ${param}\""
    fi
    sed -i "s|^GRUB_CMDLINE_LINUX=.*|${new_line}|" "$GRUB_FILE"

    echo "$marker" >> "$GRUB_FILE"

    ok "GRUB updated"
    update-grub || die "update-grub failed"
    ok "GRUB configuration updated"
}

uninstall_grub() {
    if [[ -f "$GRUB_BAK" ]]; then
        cp "$GRUB_BAK" "$GRUB_FILE"
        rm -f "$GRUB_BAK"
        ok "Restored original GRUB from backup"
    else
        sed -i '/^# virtual-monitor:/d' "$GRUB_FILE"
        sed -i 's| drm\.edid_firmware=[^ "]*||g; s| video=[^ "]*[0-9]\+e||g' "$GRUB_FILE"
        ok "Cleaned virtual-monitor parameters from GRUB"
    fi
    update-grub || die "update-grub failed"
    ok "GRUB configuration updated"
}

# ---- commands ---------------------------------------------------------
install() {
    check_root
    [[ -z "$CONNECTOR" ]] && detect_connector
    echo ""
    info "========== Virtual Monitor Install =========="
    info "Connector: ${CONNECTOR}  |  ${RES_W}x${RES_H}@${REFRESH}Hz"
    echo ""

    generate_edid
    install_grub

    echo ""
    ok "Installation complete! Reboot to activate."
    read -rp "$(info 'Reboot now? [y/N]: ')" ans
    [[ "${ans,,}" =~ ^y ]] && reboot
}

uninstall() {
    check_root
    echo ""
    info "========== Virtual Monitor Uninstall =========="
    echo ""

    if [[ -d "$EDID_DIR" ]]; then
        rm -f "$EDID_DIR"/*.bin
        rmdir "$EDID_DIR" 2>/dev/null || true
        ok "Removed EDID files"
    else
        info "No EDID directory found"
    fi

    uninstall_grub

    echo ""
    ok "Uninstall complete. Reboot to remove the virtual display."
    read -rp "$(info 'Reboot now? [y/N]: ')" ans
    [[ "${ans,,}" =~ ^y ]] && reboot
}

usage() {
    cat <<EOF
Usage: sudo bash $0 <command> [options]

Commands:
  install          Create and enable virtual display
  uninstall        Remove virtual display and restore config

Options:
  -c, --connector CONN   DRM connector (e.g. HDMI-A-1, DP-1). Auto-detected.
  -r, --resolution WxH   Resolution (default: 1920x1080)
  -R, --refresh Hz       Refresh rate (default: 60)
  -h, --help             Show this help

Examples:
  sudo bash $0 install
  sudo bash $0 install -r 2560x1440 -R 75
  sudo bash $0 install -c HDMI-A-1 -r 3840x2160 -R 30
  sudo bash $0 uninstall
EOF
    exit 0
}

# ---- parse args -------------------------------------------------------
[[ $# -eq 0 ]] && usage

while [[ $# -gt 0 ]]; do
    case "$1" in
        install|uninstall) MODE="$1"; shift ;;
        -c|--connector) CONNECTOR="$2"; shift 2 ;;
        -r|--resolution)
            if [[ "$2" =~ ^([0-9]+)x([0-9]+)$ ]]; then
                RES_W="${BASH_REMATCH[1]}"
                RES_H="${BASH_REMATCH[2]}"
            else
                die "Invalid resolution: $2 (use WxH, e.g. 1920x1080)"
            fi
            shift 2 ;;
        -R|--refresh)
            [[ "$2" =~ ^[0-9]+$ ]] || die "Invalid refresh rate: $2"
            REFRESH="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) die "Unknown option: $1" ;;
    esac
done

case "$MODE" in
    install)   install ;;
    uninstall) uninstall ;;
    *)         usage ;;
esac
