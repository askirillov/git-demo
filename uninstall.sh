#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_LINK_FILE="${SCRIPT_DIR}/client-link.txt"

err() {
  echo "ERROR: $*" >&2
}

info() {
  echo "==> $*"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    err "Скрипт должен быть запущен от root. Используйте: sudo bash uninstall.sh"
    exit 1
  fi
}

main() {
  require_root

  info "Останавливаем и отключаем Xray"
  systemctl stop xray 2>/dev/null || true
  systemctl disable xray 2>/dev/null || true

  info "Пробуем удалить Xray через официальный XTLS/Xray-install"
  TMP_INSTALLER="$(mktemp)"
  if curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh -o "${TMP_INSTALLER}"; then
    bash "${TMP_INSTALLER}" --remove || true
  else
    err "Не удалось скачать официальный uninstall-скрипт. Выполняем ручную очистку."
  fi
  rm -f "${TMP_INSTALLER}"

  info "Удаляем оставшиеся файлы Xray и созданные конфигурации"
  rm -rf \
    /usr/local/bin/xray \
    /usr/local/etc/xray \
    /usr/local/share/xray \
    /var/log/xray \
    /etc/systemd/system/xray.service \
    /etc/systemd/system/xray@.service \
    /etc/systemd/system/multi-user.target.wants/xray.service

  rm -f "${CLIENT_LINK_FILE}"

  info "Обновляем systemd"
  systemctl daemon-reload
  systemctl reset-failed xray 2>/dev/null || true

  info "Удаляем правило ufw для 443/tcp, если оно было создано"
  ufw delete allow 443/tcp 2>/dev/null || true

  echo
  echo "Удаление завершено. Правило ufw для 22/tcp оставлено, чтобы не потерять SSH-доступ."
}

main "$@"
