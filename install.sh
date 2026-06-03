#!/usr/bin/env bash
set -Eeuo pipefail

SNI="www.microsoft.com"
DEST="www.microsoft.com:443"
XRAY_CONFIG_DIR="/usr/local/etc/xray"
XRAY_CONFIG_FILE="${XRAY_CONFIG_DIR}/config.json"
XRAY_BIN="/usr/local/bin/xray"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_LINK_FILE="${SCRIPT_DIR}/client-link.txt"
SERVER_NAME="xray-vless-reality"

err() {
  echo "ERROR: $*" >&2
}

info() {
  echo "==> $*"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    err "Скрипт должен быть запущен от root. Используйте: sudo bash install.sh"
    exit 1
  fi
}

check_port_443_free() {
  if command -v ss >/dev/null 2>&1; then
    if ss -H -ltn '( sport = :443 )' | grep -q .; then
      err "Порт 443 уже занят. Освободите порт и запустите install.sh снова."
      ss -H -ltnp '( sport = :443 )' || true
      exit 1
    fi
  elif command -v lsof >/dev/null 2>&1; then
    if lsof -iTCP:443 -sTCP:LISTEN -P -n >/dev/null 2>&1; then
      err "Порт 443 уже занят. Освободите порт и запустите install.sh снова."
      lsof -iTCP:443 -sTCP:LISTEN -P -n || true
      exit 1
    fi
  else
    err "Не удалось проверить порт 443: не найдены ss или lsof."
    exit 1
  fi
}

restart_xray_or_show_logs() {
  info "Перезапускаем Xray"
  if ! systemctl restart xray; then
    err "systemctl restart xray не сработал. Последние 50 строк логов:"
    journalctl -u xray -n 50 --no-pager || true
    exit 1
  fi
}

main() {
  require_root

  info "Останавливаем Xray перед проверкой порта 443, если сервис уже установлен"
  systemctl stop xray || true

  info "Проверяем, свободен ли порт 443"
  check_port_443_free

  export DEBIAN_FRONTEND=noninteractive

  info "Обновляем индекс пакетов"
  apt-get update

  info "Устанавливаем зависимости: curl, wget, unzip, ufw, jq"
  apt-get install -y curl wget unzip ufw jq ca-certificates

  info "Устанавливаем Xray-core через официальный XTLS/Xray-install"
  bash -c "$(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)"

  if [[ ! -x "${XRAY_BIN}" ]]; then
    err "Xray не найден по пути ${XRAY_BIN} после установки."
    exit 1
  fi

  info "Генерируем UUID"
  UUID="$(${XRAY_BIN} uuid)"

  info "Генерируем Reality x25519 private/public key"
  X25519_OUTPUT="$(${XRAY_BIN} x25519)"
  PRIVATE_KEY="$(printf '%s\n' "${X25519_OUTPUT}" | awk -F': ' '/Private key/ {print $2; exit}')"
  PUBLIC_KEY="$(printf '%s\n' "${X25519_OUTPUT}" | awk -F': ' '/Public key/ {print $2; exit}')"

  if [[ -z "${PRIVATE_KEY}" || -z "${PUBLIC_KEY}" ]]; then
    err "Не удалось получить Reality x25519 private/public key. Вывод команды:"
    printf '%s\n' "${X25519_OUTPUT}" >&2
    exit 1
  fi

  info "Генерируем shortId"
  SHORT_ID="$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')"

  info "Создаём ${XRAY_CONFIG_FILE}"
  install -d -m 755 "${XRAY_CONFIG_DIR}"
  cat > "${XRAY_CONFIG_FILE}" <<CONFIG
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "tag": "vless-reality-in",
      "listen": "0.0.0.0",
      "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "${UUID}",
            "flow": "xtls-rprx-vision"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "${DEST}",
          "xver": 0,
          "serverNames": [
            "${SNI}"
          ],
          "privateKey": "${PRIVATE_KEY}",
          "shortIds": [
            "${SHORT_ID}"
          ]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": [
          "http",
          "tls",
          "quic"
        ]
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "tag": "direct"
    },
    {
      "protocol": "blackhole",
      "tag": "block"
    }
  ]
}
CONFIG
  chmod 600 "${XRAY_CONFIG_FILE}"

  info "Проверяем конфигурацию Xray"
  "${XRAY_BIN}" run -test -config "${XRAY_CONFIG_FILE}"

  info "Включаем автозапуск Xray"
  systemctl enable xray
  restart_xray_or_show_logs

  info "Открываем порты 22 и 443 через ufw"
  ufw allow 22/tcp
  ufw allow 443/tcp
  ufw --force enable

  SERVER_IP="$(curl -fsSL --connect-timeout 5 https://api.ipify.org || hostname -I | awk '{print $1}')"
  if [[ -z "${SERVER_IP}" ]]; then
    SERVER_IP="YOUR_SERVER_IP"
  fi

  VLESS_LINK="vless://${UUID}@${SERVER_IP}:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=${SNI}&fp=chrome&pbk=${PUBLIC_KEY}&sid=${SHORT_ID}&spx=%2F&type=tcp#${SERVER_NAME}"

  printf '%s\n' "${VLESS_LINK}" > "${CLIENT_LINK_FILE}"
  chmod 600 "${CLIENT_LINK_FILE}"

  echo
  echo "============================================================"
  echo "Установка завершена."
  echo "UUID: ${UUID}"
  echo "Public key: ${PUBLIC_KEY}"
  echo "Short ID: ${SHORT_ID}"
  echo "Server IP: ${SERVER_IP}"
  echo "SNI: ${SNI}"
  echo "VLESS link: ${VLESS_LINK}"
  echo
  echo "Ссылка сохранена в файл: ${CLIENT_LINK_FILE}"
  echo "Проверка статуса: systemctl status xray"
  echo "Логи: journalctl -u xray -e"
  echo "============================================================"
}

main "$@"
