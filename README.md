# Xray VLESS TCP REALITY installer для Ubuntu 24.04 / Debian 12

Готовый минимальный проект для автоматической установки собственного VPN-сервера **Xray-core VLESS TCP REALITY** на VPS с Ubuntu 24.04 или Debian 12.

Скрипт `install.sh`:

- обновляет индекс пакетов через `apt-get update`;
- устанавливает `curl`, `wget`, `unzip`, `ufw`, `jq`;
- устанавливает Xray-core через официальный `XTLS/Xray-install`;
- генерирует UUID;
- генерирует Reality `x25519` private/public key;
- генерирует `shortId`;
- создаёт `/usr/local/etc/xray/config.json` и выставляет права `600`;
- настраивает inbound `VLESS TCP REALITY` на порт `443`;
- использует `flow=xtls-rprx-vision`;
- формирует клиентскую ссылку с `fp=chrome`;
- использует `SNI=www.microsoft.com`;
- использует `dest=www.microsoft.com:443`;
- включает автозапуск `xray`;
- перезапускает `xray`;
- открывает порты `22/tcp` и `443/tcp` через `ufw`;
- выводит отдельными строками UUID, Public key, Short ID, Server IP, SNI и готовую `vless://` ссылку, затем сохраняет её в `client-link.txt`.

## Требования

- Чистый VPS с Ubuntu 24.04 или Debian 12.
- Root-доступ или пользователь с `sudo`.
- Свободный порт `443`.
- Доступ к интернету с сервера.

> Важно: если порт `443` уже занят, установка остановится и покажет процесс, который слушает порт.

## 1. Подключение к VPS по SSH

Подключитесь к серверу из терминала на вашем компьютере:

```bash
ssh root@YOUR_SERVER_IP
```

Если вы используете пользователя с sudo:

```bash
ssh username@YOUR_SERVER_IP
```

Затем перейдите в root-сессию:

```bash
sudo -i
```

## 2. Загрузка файлов проекта

Скопируйте файлы проекта на сервер любым удобным способом.

Пример через `scp` с вашего компьютера:

```bash
scp install.sh uninstall.sh README.md root@YOUR_SERVER_IP:/root/
```

Если вы скачали репозиторий как архив из GitHub, распакуйте его на сервере и перейдите в папку с `install.sh`.

## 3. Запуск установки

На сервере выполните:

```bash
cd /root
chmod +x install.sh uninstall.sh
sudo bash install.sh
```

Если вы уже root, можно так:

```bash
bash install.sh
```

В конце установки скрипт отдельно выведет `UUID`, `Public key`, `Short ID`, `Server IP`, `SNI` и готовую ссылку вида:

```text
vless://UUID@SERVER_IP:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&spx=%2F&type=tcp#xray-vless-reality
```

Также ссылка будет сохранена в файл:

```bash
/root/client-link.txt
```

Если вы запускали скрипт из другой папки, файл `client-link.txt` появится рядом с `install.sh`.

## 4. Как скопировать vless-ссылку

Показать ссылку в терминале:

```bash
cat /root/client-link.txt
```

Скопируйте всю строку, начиная с `vless://`.

Если файл находится не в `/root`, перейдите в папку со скриптом и выполните:

```bash
cat client-link.txt
```

## 5. Импорт ссылки в клиенты

### V2RayN

1. Откройте V2RayN.
2. Нажмите **Servers** / **Серверы**.
3. Выберите **Import bulk URL from clipboard** или **Импорт из буфера обмена**.
4. Вставьте или предварительно скопируйте `vless://` ссылку.
5. Выберите добавленный профиль и подключитесь.

### Nekoray

1. Откройте Nekoray.
2. Скопируйте `vless://` ссылку в буфер обмена.
3. Нажмите **Program** → **Add profile from clipboard**.
4. Выберите импортированный профиль.
5. Нажмите **Start**.

### Hiddify

1. Откройте Hiddify.
2. Нажмите **Add Profile**.
3. Выберите импорт из буфера обмена или вставку ссылки.
4. Вставьте `vless://` ссылку.
5. Сохраните профиль и подключитесь.

### v2rayNG

1. Откройте v2rayNG на Android.
2. Скопируйте `vless://` ссылку в буфер обмена.
3. Нажмите **+**.
4. Выберите **Import config from clipboard**.
5. Выберите созданный профиль и нажмите кнопку подключения.

## 6. Проверка статуса Xray

Проверить статус сервиса:

```bash
systemctl status xray
```

Если сервис работает, вы увидите статус `active (running)`.

## 7. Просмотр логов

Показать последние записи логов Xray:

```bash
journalctl -u xray -e
```

Показать последние 50 строк без интерактивного режима:

```bash
journalctl -u xray -n 50 --no-pager
```

## 8. Удаление

Для полного удаления Xray и созданных файлов выполните:

```bash
sudo bash uninstall.sh
```

Скрипт удалит Xray, конфигурацию, логи, systemd unit-файлы и `client-link.txt`.
Правило `ufw` для `443/tcp` будет удалено. Правило `22/tcp` останется, чтобы не потерять SSH-доступ.

## 9. Что делать при ошибках

### Скрипт запущен не от root

Запустите установку так:

```bash
sudo bash install.sh
```

### Порт 443 занят

Проверьте, кто слушает порт:

```bash
ss -ltnp '( sport = :443 )'
```

Остановите конфликтующий сервис, например nginx или apache, и запустите установку снова.

### Xray не перезапустился

`install.sh` автоматически покажет последние 50 строк логов. Дополнительно можно выполнить:

```bash
journalctl -u xray -n 50 --no-pager
```

## Файлы проекта

- `install.sh` — автоматическая установка и вывод клиентской ссылки.
- `uninstall.sh` — удаление Xray и созданных файлов.
- `README.md` — инструкция по установке, проверке и импорту.
- Бинарные архивы (`*.zip`, `*.exe`, `*.apk`) не добавляются в git. Если нужен архив для переноса на VPS, создайте его локально командой `zip -9 xray-vless-reality-installer.zip install.sh uninstall.sh README.md`.
