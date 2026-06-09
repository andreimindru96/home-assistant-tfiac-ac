#!/usr/bin/env bash
set -Eeuo pipefail

# Defaults for this Home Assistant/Yunohost install. Override with flags or env vars.
HA_HOST="${HA_HOST:-homeassistant.local}"
HA_USER="${HA_USER:-${USER:-homeassistant}}"
SSH_PORT="${SSH_PORT:-22}"
HA_CONFIG="${HA_CONFIG:-/config}"
REMOTE_OWNER="${REMOTE_OWNER:-homeassistant}"
REMOTE_GROUP="${REMOTE_GROUP:-homeassistant}"
DIR_MODE="${DIR_MODE:-770}"
FILE_MODE="${FILE_MODE:-660}"
BECOME_METHOD="${BECOME_METHOD:-su}"
SU_COMMAND="${SU_COMMAND:-su}"
REMOTE_STAGE="${REMOTE_STAGE:-/tmp/tfiac_local_deploy}"
SSH_CONTROL="${SSH_CONTROL:-1}"
DELETE_REMOTE="${DELETE_REMOTE:-1}"
DRY_RUN="${DRY_RUN:-0}"
RESTART_HA="${RESTART_HA:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/custom_components/tfiac_local/"
REMOTE_DIR="$HA_CONFIG/custom_components/tfiac_local"
LOCAL_TEMP_SCRIPT=""
LOCAL_CONTROL_DIR=""
SSH_CONTROL_PATH=""
SSH_ARGS=()
RSYNC_RSH=""

cleanup_local_temp() {
  if [[ -n "$LOCAL_TEMP_SCRIPT" ]]; then
    rm -f "$LOCAL_TEMP_SCRIPT"
  fi
  if [[ -n "$SSH_CONTROL_PATH" && -S "$SSH_CONTROL_PATH" ]]; then
    ssh -p "$SSH_PORT" -S "$SSH_CONTROL_PATH" -O exit "$REMOTE" >/dev/null 2>&1 || true
  fi
  if [[ -n "$LOCAL_CONTROL_DIR" ]]; then
    rm -rf "$LOCAL_CONTROL_DIR"
  fi
}

trap cleanup_local_temp EXIT

usage() {
  cat <<EOF
Deploy the tfiac_local custom component to Home Assistant over SSH/rsync.

Usage:
  ./deploy_tfiac_local.sh [options]

Options:
  --host HOST              Home Assistant LAN hostname/IP. Default: $HA_HOST
  --user USER              SSH login user. Default: $HA_USER
  --port PORT              SSH port. Default: $SSH_PORT
  --config PATH            Home Assistant config path. Default: $HA_CONFIG
  --owner OWNER            Remote owner after deploy. Default: $REMOTE_OWNER
  --group GROUP            Remote group after deploy. Default: $REMOTE_GROUP
  --dir-mode MODE          Directory mode after deploy. Default: $DIR_MODE
  --file-mode MODE         File mode after deploy. Default: $FILE_MODE
  --become su|sudo|direct|auto
                           Root method. Default: $BECOME_METHOD
  --su-command COMMAND     su command to use for --become su. Default: $SU_COMMAND
  --stage PATH             Normal-user staging path for --become su. Default: $REMOTE_STAGE
  --no-ssh-control         Disable SSH connection reuse.
  --no-delete              Do not delete remote files that no longer exist locally.
  --dry-run                Show planned actions without changing remote files.
  --restart                Restart Home Assistant after deploy.
  -h, --help               Show this help.

Examples:
  ./deploy_tfiac_local.sh --host 192.168.1.50 --user your-yunohost-user
  ./deploy_tfiac_local.sh --host 192.168.1.50 --user your-yunohost-user --restart
  BECOME_METHOD=sudo ./deploy_tfiac_local.sh --host homeassistant.local --user root
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HA_HOST="$2"
      shift 2
      ;;
    --user)
      HA_USER="$2"
      shift 2
      ;;
    --port)
      SSH_PORT="$2"
      shift 2
      ;;
    --config)
      HA_CONFIG="$2"
      shift 2
      ;;
    --owner)
      REMOTE_OWNER="$2"
      shift 2
      ;;
    --group)
      REMOTE_GROUP="$2"
      shift 2
      ;;
    --dir-mode)
      DIR_MODE="$2"
      shift 2
      ;;
    --file-mode)
      FILE_MODE="$2"
      shift 2
      ;;
    --become)
      BECOME_METHOD="$2"
      shift 2
      ;;
    --sudo)
      case "$2" in
        yes) BECOME_METHOD="sudo" ;;
        no) BECOME_METHOD="direct" ;;
        auto) BECOME_METHOD="auto" ;;
        *)
          echo "--sudo must be one of: auto, yes, no" >&2
          exit 2
          ;;
      esac
      shift 2
      ;;
    --su-command)
      SU_COMMAND="$2"
      shift 2
      ;;
    --stage)
      REMOTE_STAGE="$2"
      shift 2
      ;;
    --no-ssh-control)
      SSH_CONTROL=0
      shift
      ;;
    --no-delete)
      DELETE_REMOTE=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --restart)
      RESTART_HA=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

REMOTE_DIR="$HA_CONFIG/custom_components/tfiac_local"
REMOTE="$HA_USER@$HA_HOST"
STAGE_SOURCE="$REMOTE_STAGE/source"
STAGE_SCRIPT="$REMOTE_STAGE/apply_as_root.sh"

quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

shell_assign() {
  printf "%s=%s\n" "$1" "$(quote "$2")"
}

remote_run() {
  ssh "${SSH_ARGS[@]}" "$REMOTE" "$1"
}

remote_run_tty() {
  ssh -tt "${SSH_ARGS[@]}" "$REMOTE" "$1"
}

remote_run_quiet() {
  ssh "${SSH_ARGS[@]}" "$REMOTE" "$1" >/dev/null 2>&1
}

need_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required local command: $1" >&2
    exit 1
  fi
}

validate_stage_path() {
  case "$REMOTE_STAGE" in
    ""|"/"|"/tmp"|"/var"|"/home"|"/root"|"/config")
      echo "Unsafe staging path: $REMOTE_STAGE" >&2
      exit 2
      ;;
  esac
}

configure_ssh_transport() {
  SSH_ARGS=(-p "$SSH_PORT")
  RSYNC_RSH="ssh -p $SSH_PORT"

  if [[ "$SSH_CONTROL" != "1" ]]; then
    return
  fi

  need_command mktemp
  LOCAL_CONTROL_DIR="$(mktemp -d)"
  SSH_CONTROL_PATH="$LOCAL_CONTROL_DIR/control"
  SSH_ARGS+=(
    -o ControlMaster=auto
    -o ControlPersist=300
    -o "ControlPath=$SSH_CONTROL_PATH"
  )
  RSYNC_RSH="ssh -p $SSH_PORT -o ControlMaster=auto -o ControlPersist=300 -o ControlPath=$SSH_CONTROL_PATH"
}

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Source directory not found: $SOURCE_DIR" >&2
  exit 1
fi

case "$BECOME_METHOD" in
  auto|direct|sudo|su) ;;
  *)
    echo "--become must be one of: auto, direct, sudo, su" >&2
    exit 2
    ;;
esac

need_command ssh
need_command rsync
configure_ssh_transport

if [[ "$BECOME_METHOD" == "auto" ]]; then
  if remote_run_quiet 'test "$(id -u)" -eq 0'; then
    BECOME_METHOD="direct"
  elif remote_run_quiet "sudo -n true"; then
    BECOME_METHOD="sudo"
  else
    BECOME_METHOD="su"
  fi
fi

if [[ "$BECOME_METHOD" == "su" ]]; then
  need_command mktemp
fi

echo "Deploying tfiac_local"
echo "  local:  $SOURCE_DIR"
echo "  remote: $REMOTE:$REMOTE_DIR"
echo "  owner:  $REMOTE_OWNER:$REMOTE_GROUP"
echo "  modes:  directories $DIR_MODE, files $FILE_MODE"
echo "  become: $BECOME_METHOD"
if [[ "$SSH_CONTROL" == "1" ]]; then
  echo "  ssh:    connection reuse enabled"
else
  echo "  ssh:    connection reuse disabled"
fi

q_config="$(quote "$HA_CONFIG")"
q_config_yaml="$(quote "$HA_CONFIG/configuration.yaml")"
q_custom="$(quote "$HA_CONFIG/custom_components")"
q_remote_dir="$(quote "$REMOTE_DIR")"
q_owner_group="$(quote "$REMOTE_OWNER:$REMOTE_GROUP")"
q_dir_mode="$(quote "$DIR_MODE")"
q_file_mode="$(quote "$FILE_MODE")"
q_stage="$(quote "$REMOTE_STAGE")"
q_stage_source="$(quote "$STAGE_SOURCE")"
q_stage_script="$(quote "$STAGE_SCRIPT")"

if [[ "$DRY_RUN" == "1" ]]; then
  echo
  echo "Dry run only. No remote files will be changed."
  echo "Would copy these files:"
  find "$SOURCE_DIR" -maxdepth 2 -type f -printf "  %P\n" | sort
  if [[ "$BECOME_METHOD" == "su" ]]; then
    echo
    echo "Would upload to staging path: $REMOTE_STAGE"
    echo "Would ask for the root password through su, then copy into: $REMOTE_DIR"
  else
    echo
    echo "Would rsync directly into: $REMOTE_DIR"
  fi
  exit 0
fi

build_root_apply_script() {
  local output="$1"
  {
    echo "#!/bin/sh"
    echo "set -eu"
    shell_assign HA_CONFIG "$HA_CONFIG"
    shell_assign REMOTE_DIR "$REMOTE_DIR"
    shell_assign STAGE_SOURCE "$STAGE_SOURCE"
    shell_assign REMOTE_OWNER "$REMOTE_OWNER"
    shell_assign REMOTE_GROUP "$REMOTE_GROUP"
    shell_assign DIR_MODE "$DIR_MODE"
    shell_assign FILE_MODE "$FILE_MODE"
    shell_assign DELETE_REMOTE "$DELETE_REMOTE"
    shell_assign RESTART_HA "$RESTART_HA"
    cat <<'ROOT_SCRIPT'

echo
echo "Validating Home Assistant config path:"
if [ ! -d "$HA_CONFIG" ]; then
  echo "ERROR: Config path does not exist or is not a directory: $HA_CONFIG" >&2
  exit 1
fi
if [ ! -f "$HA_CONFIG/configuration.yaml" ]; then
  echo "ERROR: Config path is missing configuration.yaml: $HA_CONFIG" >&2
  echo "Use --config with the folder that contains configuration.yaml." >&2
  exit 1
fi
echo "Config path looks valid: $HA_CONFIG"

echo
echo "Current remote permissions:"
ls -ld "$HA_CONFIG" 2>/dev/null || true
ls -ld "$(dirname "$REMOTE_DIR")" "$REMOTE_DIR" 2>/dev/null || true
if [ -d "$REMOTE_DIR" ]; then
  find "$REMOTE_DIR" -maxdepth 2 -printf '%M %u:%g %p\n'
fi

mkdir -p "$REMOTE_DIR"

rsync_args="-a --chmod=D$DIR_MODE,F$FILE_MODE"
if [ "$DELETE_REMOTE" = "1" ]; then
  rsync_args="$rsync_args --delete"
fi

echo
echo "Copying from staging into Home Assistant config:"
# shellcheck disable=SC2086
rsync $rsync_args "$STAGE_SOURCE/" "$REMOTE_DIR/"

echo
echo "Restoring owner and permissions:"
chown -R "$REMOTE_OWNER:$REMOTE_GROUP" "$REMOTE_DIR"
find "$REMOTE_DIR" -type d -exec chmod "$DIR_MODE" {} +
find "$REMOTE_DIR" -type f -exec chmod "$FILE_MODE" {} +

echo
echo "Final remote permissions:"
ls -ld "$REMOTE_DIR"
find "$REMOTE_DIR" -maxdepth 2 -printf '%M %u:%g %p\n'

if command -v getfacl >/dev/null 2>&1; then
  echo
  echo "Remote ACL for integration folder:"
  getfacl -p "$REMOTE_DIR"
fi

if [ "$RESTART_HA" = "1" ]; then
  echo
  echo "Restarting Home Assistant:"
  if command -v ha >/dev/null 2>&1; then
    ha core restart
  else
    echo "The 'ha' command is not available on this host. Restart Home Assistant manually."
  fi
fi
ROOT_SCRIPT
  } > "$output"
}

run_direct_or_sudo_deploy() {
  local sudo_prefix=""
  local rsync_path=()

  if [[ "$BECOME_METHOD" == "sudo" ]]; then
    sudo_prefix="sudo -n"
    rsync_path=(--rsync-path "sudo -n rsync")
  fi

  echo
  echo "Validating Home Assistant config path:"
  if ! remote_run "$sudo_prefix test -d $q_config"; then
    echo "ERROR: Config path does not exist or is not a directory: $HA_CONFIG" >&2
    exit 1
  fi
  if ! remote_run "$sudo_prefix test -f $q_config_yaml"; then
    echo "ERROR: Config path is missing configuration.yaml: $HA_CONFIG" >&2
    echo "Use --config with the folder that contains configuration.yaml." >&2
    exit 1
  fi
  echo "Config path looks valid: $HA_CONFIG"

  echo
  echo "Current remote permissions:"
  remote_run "ls -ld $q_config $q_custom $q_remote_dir 2>/dev/null || true"
  remote_run "if [ -d $q_remote_dir ]; then find $q_remote_dir -maxdepth 2 -printf '%M %u:%g %p\n'; fi"

  echo
  echo "Creating remote directory:"
  remote_run "$sudo_prefix mkdir -p $q_remote_dir"

  local rsync_args=(
    -av
    --exclude "__pycache__/"
    --exclude "*.pyc"
    --chmod "D$DIR_MODE,F$FILE_MODE"
    -e "$RSYNC_RSH"
  )

  if [[ "$DELETE_REMOTE" == "1" ]]; then
    rsync_args+=(--delete)
  fi

  if [[ ${#rsync_path[@]} -gt 0 ]]; then
    rsync_args+=("${rsync_path[@]}")
  fi

  echo
  echo "Running rsync:"
  rsync "${rsync_args[@]}" "$SOURCE_DIR" "$REMOTE:$REMOTE_DIR/"

  echo
  echo "Restoring owner and permissions after rsync:"
  remote_run "$sudo_prefix chown -R $q_owner_group $q_remote_dir"
  remote_run "$sudo_prefix find $q_remote_dir -type d -exec chmod $q_dir_mode {} +"
  remote_run "$sudo_prefix find $q_remote_dir -type f -exec chmod $q_file_mode {} +"

  echo
  echo "Final remote permissions:"
  remote_run "ls -ld $q_remote_dir"
  remote_run "find $q_remote_dir -maxdepth 2 -printf '%M %u:%g %p\n'"

  if remote_run_quiet "command -v getfacl"; then
    echo
    echo "Remote ACL for integration folder:"
    remote_run "getfacl -p $q_remote_dir"
  fi
}

run_su_deploy() {
  validate_stage_path

  LOCAL_TEMP_SCRIPT="$(mktemp)"
  build_root_apply_script "$LOCAL_TEMP_SCRIPT"

  echo
  echo "Creating normal-user staging directory:"
  remote_run "mkdir -p $q_stage_source && chmod 700 $q_stage"

  local rsync_args=(
    -av
    --delete
    --exclude "__pycache__/"
    --exclude "*.pyc"
    --chmod "D$DIR_MODE,F$FILE_MODE"
    -e "$RSYNC_RSH"
  )

  echo
  echo "Uploading integration to staging as $HA_USER:"
  rsync "${rsync_args[@]}" "$SOURCE_DIR" "$REMOTE:$STAGE_SOURCE/"

  echo
  echo "Uploading root apply script:"
  rsync -av -e "$RSYNC_RSH" "$LOCAL_TEMP_SCRIPT" "$REMOTE:$STAGE_SCRIPT"
  remote_run "chmod 700 $q_stage_script"

  echo
  echo "Applying staged files as root via su."
  echo "Enter the root password if prompted by the remote host."
  remote_run_tty "$SU_COMMAND -c $(quote "sh $STAGE_SCRIPT")"

  echo
  echo "Cleaning up staging directory:"
  remote_run "rm -rf $q_stage"
}

case "$BECOME_METHOD" in
  direct|sudo)
    run_direct_or_sudo_deploy
    ;;
  su)
    run_su_deploy
    ;;
esac

if [[ "$RESTART_HA" == "1" && "$BECOME_METHOD" != "su" ]]; then
  echo
  echo "Restarting Home Assistant:"
  remote_run "ha core restart"
elif [[ "$RESTART_HA" != "1" ]]; then
  echo
  echo "Deploy complete. Restart Home Assistant when ready."
fi
