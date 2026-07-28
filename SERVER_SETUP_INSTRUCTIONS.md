# 🖥️ Настройка сервера - Пошаговая инструкция

## Сервер: 95.81.101.148

Выполняйте эти команды по порядку. Каждый шаг проверяется перед переходом к следующему.

---

## ШАГ 1: Подключение к серверу

```bash
ssh root@95.81.101.148
```

Введите пароль от сервера.

---

## ШАГ 2: Обновление системы

```bash
# Обновите пакеты
apt update && apt upgrade -y

# Проверьте версию ОС
cat /etc/os-release
```

**Ожидаемый результат:** Система обновилась без ошибок.

---

## ШАГ 3: Установка Docker

```bash
# Скачайте скрипт установки Docker
curl -fsSL https://get.docker.com | bash

# Дождитесь завершения установки (может занять 2-5 минут)

# Добавьте root пользователя в группу docker
usermod -aG docker root

# Проверьте установку
docker --version
```

**Ожидаемый результат:** `Docker version 24.x.x`

---

## ШАГ 4: Установка Docker Compose

```bash
# Скачайте Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Сделайте файл исполняемым
chmod +x /usr/local/bin/docker-compose

# Проверьте установку
docker-compose --version
```

**Ожидаемый результат:** `Docker Compose version v2.x.x`

---

## ШАГ 5: Создание структуры директорий

```bash
# Создайте директорию проекта
mkdir -p /opt/claude-ml-trading/{data,models,logs}

# Установите права доступа
chown -R root:root /opt/claude-ml-trading
chmod -R 755 /opt/claude-ml-trading

# Проверьте создание
ls -la /opt/claude-ml-trading/
```

**Ожидаемый результат:** Видны папки `data`, `models`, `logs`

---

## ШАГ 6: Клонирование репозитория

### Вариант A: Если уже есть Git репозиторий

```bash
cd /opt/claude-ml-trading

# Клонируйте ваш репозиторий
git clone https://github.com/ВАШ_НИК/claude-ml-trading.git .

# Или если используете SSH ключи:
# git clone git@github.com:ВАШ_НИК/claude-ml-trading.git .
```

### Вариант B: Если Git репозитория ещё нет

**На вашем локальном ПК выполните:**

```bash
cd C:\Bot\claude_ml_system

# Инициализируйте Git
git init
git add .
git commit -m "Initial commit"

# Создайте репозиторий на GitHub через веб-интерфейс
# Затем добавьте remote и запушьте:
git remote add origin https://github.com/ВАШ_НИК/claude-ml-trading.git
git branch -M main
git push -u origin main
```

**Затем на сервере:**

```bash
cd /opt/claude-ml-trading
git clone https://github.com/ВАШ_НИК/claude-ml-trading.git .
```

---

## ШАГ 7: Настройка переменных окружения

### Способ 1: Создать .env файл вручную

```bash
cd /opt/claude-ml-trading

# Создайте .env файл
nano .env
```

Скопируйте содержимое из вашего локального `.env` файла и вставьте его сюда.

**Обязательные параметры:**
```env
MARKET_DATA_PROVIDER=okx
OKX_BASE_URL=https://www.okx.com
SYMBOLS=BTCUSDT
TIMEFRAME=15
MODE=paper
PAPER_START_BALANCE=10000
RISK_PER_TRADE_PCT=1.0
MAX_DRAWDOWN_PCT=15.0
POLL_SECONDS=15

# Telegram для уведомлений (опционально)
TELEGRAM_BOT_TOKEN=ваш_токен
TELEGRAM_CHAT_ID=ваш_chat_id
```

Сохраните: `Ctrl+O`, затем `Enter`, затем `Ctrl+X` для выхода.

### Способ 2: Скопировать с локального ПК

**На локальном ПК:**

```bash
scp C:/Bot/claude_ml_system/.env root@95.81.101.148:/opt/claude-ml-trading/.env
```

---

## ШАГ 8: Проверка файлов проекта

```bash
cd /opt/claude-ml-trading

# Проверьте наличие необходимых файлов
ls -la Dockerfile docker-compose.yml .env

# Должны быть видны:
# ✅ Dockerfile
# ✅ docker-compose.yml
# ✅ .env
```

Если каких-то файлов нет - они не были загружены. Загрузите их:

```bash
# Например, если нет Dockerfile:
wget https://raw.githubusercontent.com/ВАШ_НИК/claude-ml-trading/main/Dockerfile
```

---

## ШАГ 9: Первый запуск Docker контейнеров

```bash
cd /opt/claude-ml-trading

# Соберите образы
docker-compose build

# Это займёт 3-10 минут в зависимости от скорости интернета
# Будет скачан Python 3.11, установлены все зависимости
```

**Ожидаемый процесс:**
```
[+] Building 120.5s (15/15) FINISHED
 => [internal] load build definition from Dockerfile
 => [stage-0 1/7] FROM docker.io/library/python:3.11-slim
 => [2/7] COPY requirements.txt .
 => [3/7] RUN pip install --no-cache-dir -r requirements.txt
 => ...
 => exporting to image
```

После успешной сборки запустите контейнеры:

```bash
docker-compose up -d
```

**Ожидаемый результат:**
```
[+] Running 2/2
 ✔ Container claude-ml-bot      Started
 ✔ Container claude-ml-monitor  Started
```

---

## ШАГ 10: Проверка работы

```bash
# Проверьте статус контейнеров
docker-compose ps

# Ожидаемый результат:
# NAME                STATUS         PORTS
# claude-ml-bot       Up 30 seconds
# claude-ml-monitor   Up 30 seconds
```

Если статус `Up` - всё хорошо!

Если статус `Restarting` или `Exited` - смотрите логи:

```bash
# Посмотрите логи торгового бота
docker-compose logs claude-ml-trading

# Логи в реальном времени
docker-compose logs -f claude-ml-trading
```

**Типичные ошибки и решения:**

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `ModuleNotFoundError` | Нет requirements.txt | Проверьте файлы проекта |
| `FileNotFoundError` | Нет .env файла | Создайте .env (Шаг 7) |
| `Connection refused` | Нет интернета | Проверьте подключение |

---

## ШАГ 11: Настройка автозапуска

Чтобы бот запускался автоматически после перезагрузки сервера:

```bash
cd /opt/claude-ml-trading

# Docker Compose уже настроен с restart: unless-stopped
# Проверьте это в docker-compose.yml:
grep restart docker-compose.yml

# Должно быть:
# restart: unless-stopped
```

Проверьте работу после перезагрузки:

```bash
# Перезагрузите сервер
reboot

# Подождите 1-2 минуты, подключитесь снова
ssh root@95.81.101.148

# Проверьте статус контейнеров
docker ps

# Должны быть запущены:
# claude-ml-bot
# claude-ml-monitor
```

---

## ШАГ 12: Настройка деплоя с локального ПК

Теперь настройте автоматический деплой с вашего компьютера.

### На локальном ПК (Windows):

```bash
cd C:\Bot\claude_ml_system

# Отредактируйте deploy.sh, укажите правильный сервер
nano deploy.sh

# Найдите строку:
# SERVER="${1:-root@your-server.com}"
# Замените на:
# SERVER="${1:-root@95.81.101.148}"
```

### Тестовый деплой:

```bash
./deploy.sh root@95.81.101.148
```

**Ожидаемый процесс:**
```
╔══════════════════════════════════════════╗
║  Claude ML Trading System - Deployer    ║
╚══════════════════════════════════════════╝

[→] Checking git configuration...
[✓] Git configured
[→] Committing local changes...
[✓] Changes committed
[→] Pushing to repository...
[✓] Code pushed
[→] Deploying to server: root@95.81.101.148
[→] Uploading project files to server...
[→] Executing deployment commands on server...
[Server] Building and starting containers...
[Server] Deployment complete!
[✓] Deployment to root@95.81.101.148 completed!
```

---

## ✅ Чеклист проверки

Пройдитесь по списку:

- [ ] Docker установлен (`docker --version`)
- [ ] Docker Compose установлен (`docker-compose --version`)
- [ ] Директория создана (`ls /opt/claude-ml-trading`)
- [ ] Проект клонирован из Git
- [ ] .env файл создан и заполнен
- [ ] Все файлы на месте (Dockerfile, docker-compose.yml)
- [ ] Контейнеры запущены (`docker-compose ps`)
- [ ] Логи чистые (`docker-compose logs`)
- [ ] Автозапуск работает (проверка после reboot)
- [ ] Деплой с локального ПК работает (`./deploy.sh`)

---

## 📊 Полезные команды для мониторинга

```bash
# Статус контейнеров
docker-compose ps

# Логи в реальном времени
docker-compose logs -f claude-ml-trading

# Использование ресурсов
docker stats claude-ml-bot

# Вход в контейнер для отладки
docker exec -it claude-ml-bot bash

# Перезапуск сервиса
docker-compose restart

# Остановка всех сервисов
docker-compose down

# Запуск заново
docker-compose up -d

# Просмотр последних логов
docker-compose logs --tail=50 claude-ml-trading
```

---

## 🆘 Если что-то пошло не так

### Проблема: Контейнер не запускается

```bash
# Посмотрите полные логи
docker-compose logs claude-ml-trading

# Проверьте конфигурацию
docker-compose config

# Попробуйте пересобрать
docker-compose build --no-cache
docker-compose up -d
```

### Проблема: Ошибка в коде

```bash
# Исправьте код на локальном ПК
# Затем запуште изменения
git add .
git commit -m "Fix: описание исправления"
git push

# На сервере обновите
cd /opt/claude-ml-trading
git pull
docker-compose build --no-cache
docker-compose up -d
```

Или просто запустите с локального ПК:
```bash
./deploy.sh root@95.81.101.148
```

---

## 📞 Следующие шаги

После успешной настройки:

1. **Настройте Telegram уведомления** - добавьте токен в .env
2. **Протестируйте торговлю** - запустите в paper mode
3. **Мониторьте логи** - первые 24 часа следите за работой
4. **Настройте бэкапы** - скрипт для сохранения моделей

---

**Готово!** Ваш сервер полностью настроен для автоматического деплоя. 🎉

Теперь любое изменение кода на локальном ПК можно отправить на сервер командой:
```bash
./deploy.sh root@95.81.101.148
```
