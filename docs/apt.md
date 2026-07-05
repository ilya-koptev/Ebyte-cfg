# Установка и обновление через APT

Проект собирается в **.deb-пакет** `ebyte-cfg` и публикуется в **APT-репозиторий,
раздаваемый через `raw.githubusercontent.com`** (файлы лежат в ветке `apt`). После
разовой настройки источника обновления идут штатно: **`apt update && apt upgrade`**
подтянет свежую версию. GitHub Pages не требуется.

## Как это работает

- При каждом `push` в `main` GitHub Actions
  ([.github/workflows/release.yml](../.github/workflows/release.yml)) собирает
  `ebyte-cfg_1.0.<номер-сборки>_all.deb`, формирует плоский APT-репозиторий и
  публикует его force-push'ем в ветку **`apt`** (раздаётся через
  `raw.githubusercontent.com`).
- Версия авто-инкрементится (`1.0.<run>`), поэтому `apt upgrade` всегда видит
  более новую версию.
- Пакет ставит:
  - `/mnt/data/root/ebyte/ebyte_core.py`, `ebyte_cli.py`
  - `/etc/wb-rules/ebyte_config.js` (wb-rules перечитает сам)
  - `/etc/default/ebyte-cfg` — настройки `IFACE`/`PORT485` (conffile, **переживает
    обновления**).

## Разовая подготовка репозитория (в GitHub, делается один раз)

Ничего вручную настраивать не нужно — при первом `push` в `main` workflow сам
соберёт пакет и создаст ветку `apt` с репозиторием. Достаточно, чтобы Actions были
включены (по умолчанию включены). Адрес репозитория:
`https://raw.githubusercontent.com/ilya-koptev/Ebyte-cfg/apt/`.

## Разовая настройка на контроллере

```sh
echo 'deb [trusted=yes] https://raw.githubusercontent.com/ilya-koptev/Ebyte-cfg/apt/ ./' \
    > /etc/apt/sources.list.d/ebyte-cfg.list
apt update
apt install ebyte-cfg
```
(`[trusted=yes]` — репозиторий без GPG-подписи; для личного инструмента ок. При
желании можно добавить подпись позже.)

При необходимости поправь интерфейс/порт под своё железо:
```sh
nano /etc/default/ebyte-cfg      # IFACE=..., PORT485=...
```

## Обновление

```sh
apt update && apt upgrade
```
Обновится и `ebyte-cfg` (вместе с остальными пакетами). wb-rules перечитает
устройство автоматически — перезапуск не нужен. Настройки в `/etc/default/ebyte-cfg`
и в самом EBYTE не затрагиваются.

## Локальная сборка пакета (без CI)

На любом Debian-хосте (нужен `dpkg-deb`):
```sh
bash packaging/build-deb.sh 1.0.0
sudo dpkg -i ebyte-cfg_1.0.0_all.deb
```
