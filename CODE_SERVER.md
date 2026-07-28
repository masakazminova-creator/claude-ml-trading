# 🤖 Claude ML Trading System - Code Server Setup Guide

## 📋 Оглавление
1. [Обзор архитектуры](#обзор-архитектуры)
2. [Настройка сервера (однократно)](#настройка-сервера)
3. [Как я управляю проектом удалённо](#удалённое-управление)
4. [Команды для ручной настройки](#ручная-настройка)
5. [Troubleshooting](#troubleshooting)

---

## Обзор архитектуры

```
┌─────────────────────────────────────────────────────────────┐
│                    Ваш локальный ПК                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐  │
│  │  VS Code │    │ Git Bash │    │ deploy.sh скрипт     │  │
│  └────┬─────┘    └────┬─────┘    └──────────┬───────────┘  │
│       │                │                      │              │
└───────┼────────────────┼──────────────────────┼──────────────┘
        │                │                      │
        ▼                ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   GitHub/GitLab                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Repository: claude-ml-trading                       │   │
│  │  Branches: main (production), develop (staging)      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
        │
        │ Webhook / Polling
        ▼
┌─────────────────────────────────────────────────────────────┐
│              Ваш сервер (95.81.101.148)                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Docker Containers:                                  │   │
│  │  • claude-ml-bot (main trading bot)                  │   │
│  │  • claude-ml-monitor (health checks)                 │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Volumes:                                            │   │
│  │  • /opt/claude-ml/data  (market data)                │   │
│  │  • /opt/claude-ml/models (trained models)            │   │
│  │  • /opt/claude-ml/logs  (runtime logs)               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Настройка сервера

### Шаг 1: Подключение к серверу

```bash
# Подключитесь к серверу по SSH
ssh root@95.81.101.148
```

### Шаг 2: Установка Docker и Docker Compose

```bash
# Обновите систему
apt update && apt upgrade -y

# Установите Docker
curl -fsSL https://get.docker.com | bash

# Добавьте текущего пользователя в группу docker
usermod -aG docker $USER

# Установите Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Проверьте установку
docker --version
docker-compose --version

# Выйдите и войдите снова для применения прав
exit
```

### Шаг 3: Создание директории проекта

```bash
# Создайте структуру директорий
mkdir -p /opt/claude-ml-trading/{data,models,logs}
cd /opt/claude-ml-trading

# Установите права
chown -R $USER:$USER /opt/claude-ml-trading
chmod -R 755 /opt/claude-ml-trading
```

### Шаг 4: Клонирование репозитория

**Вариант A: Если уже есть Git репозиторий**

```bash
cd /opt/claude-ml-trading
git clone <your-git-repo-url> .
```

**Вариант B: Создать новый репозиторий на GitHub**

```bash
# На вашем локальном ПК:
cd C:\Bot\claude_ml_system
git init
git add .
git commit -m "Initial commit: Claude ML Trading System"

# Создайте репозиторий на GitHub через веб-интерфейс
# Затем добавьте remote:
git remote add origin https://github.com/YOUR_USERNAME/claude-ml-trading.git
git push -u origin main
```

### Шаг 5: Настройка переменных окружения

```bash
# На сервере создайте .env файл
cd /opt/claude-ml-trading
nano .env

# Скопируйте содержимое из вашего локального .env файла
# Или используйте готовый шаблон
```

### Шаг 6: Первый запуск

```bash
cd /opt/claude-ml-trading

# Соберите и запустите контейнеры
docker-compose build
docker-compose up -d

# Проверьте статус
docker-compose ps

# Посмотрите логи
docker-compose logs -f claude-ml-trading
```

---

## Как я управляю проектом удалённо

### Автоматический деплой (рекомендуется)

После настройки вы можете обновлять проект одной командой:

```bash
# На вашем локальном ПК
cd C:\Bot\claude_ml_system

# Запустите скрипт деплоя
./deploy.sh root@95.81.101.148
```

Этот скрипт автоматически:
1. ✅ Коммитит все изменения
2. ✅ Пушит в Git репозиторий
3. ✅ Копирует файлы на сервер через rsync
4. ✅ Пересобирает Docker контейнеры
5. ✅ Перезапускает сервис
6. ✅ Показывает логи

### Ручное управление через Git

```bash
# Внесите изменения в код
git add .
git commit -m "Update: описание изменений"
git push origin main

# На сервере (через SSH):
cd /opt/claude-ml-trading
git pull
docker-compose build --no-cache
docker-compose up -d
```

### Что я могу делать автоматически:

✅ **Изменение кода**: Я могу редактировать любые файлы проекта
✅ **Обновление зависимостей**: Изменение requirements.txt и автоматическая переустановка
✅ **Конфигурация**: Обновление .env файла
✅ **Мониторинг**: Чтение логов и проверка статуса
✅ **Тестирование**: Запуск тестов перед деплоем
✅ **Бэкапы**: Создание бэкапов моделей и данных

---

## Ручная настройка

### Полезные команды Docker

```bash
# Просмотр запущенных контейнеров
docker ps

# Просмотр всех контейнеров (включая остановленные)
docker ps -a

# Логи контейнера
docker logs claude-ml-bot -f

# Перезапуск сервиса
docker-compose restart

# Остановка всех сервисов
docker-compose down

# Запуск с пересборкой
docker-compose build --no-cache
docker-compose up -d

# Вход в контейнер для отладки
docker exec -it claude-ml-bot bash

# Использование ресурсов
docker stats claude-ml-bot
```

### Управление процессом

```bash
# Проверить, что контейнер работает
docker-compose ps

# Остановить торговый бот
docker-compose stop claude-ml-trading

# Запустить заново
docker-compose start claude-ml-trading

# Полное удаление контейнеров
docker-compose down -v
```

### Мониторинг системы

```bash
# Статистика использования ресурсов
docker stats

# Логи торгового бота
docker-compose logs -f claude-ml-trading

# Последние 100 строк логов
docker-compose logs --tail=100 claude-ml-trading

# Проверка здоровья контейнера
docker inspect --format='{{.State.Health.Status}}' claude-ml-bot
```

---

## Troubleshooting

### Проблема: Контейнер не запускается

```bash
# Проверьте логи
docker-compose logs claude-ml-trading

# Проверьте наличие .env файла
ls -la /opt/claude-ml-trading/.env

# Проверьте синтаксис docker-compose.yml
docker-compose config
```

### Проблема: Нет данных в логах

```bash
# Проверьте права доступа
ls -la /opt/claude-ml-trading/logs/

# Исправьте права
chown -R $USER:$USER /opt/claude-ml-trading/logs
chmod -R 755 /opt/claude-ml-trading/logs
```

### Проблема: Модели не сохраняются

```bash
# Проверьте volume mapping
docker inspect claude-ml-bot | grep -A 10 Mounts

# Должно быть:
# "Source": "/opt/claude-ml-trading/models"
# "Destination": "/app/models"
```

### Проблема: Ошибка подключения к API

```bash
# Проверьте интернет-соединение
docker exec claude-ml-bot ping -c 3 api.okx.com

# Проверьте .env файл
docker exec claude-ml-bot cat .env | grep OKX_BASE_URL
```

### Проблема: Высокое использование памяти

```bash
# Ограничьте ресурсы в docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '1.0'

# Перезапустите с новыми лимитами
docker-compose up -d
```

---

## Быстрый старт (шпаргалка)

### Для первого развёртывания:

```bash
# 1. На сервере
ssh root@95.81.101.148
apt update && apt install -y curl git
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER
exit

# 2. На локальном ПК
cd C:\Bot\claude_ml_system
git init
git add .
git commit -m "Initial commit"

# Создайте репозиторий на GitHub
git remote add origin <your-repo-url>
git push -u origin main

# 3. На сервере
cd /opt
git clone <your-repo-url> claude-ml-trading
cd claude-ml-trading
cp .env.example .env  # или отредактируйте .env
docker-compose build
docker-compose up -d
```

### Для обновления:

```bash
# На локальном ПК
cd C:\Bot\claude_ml_system
./deploy.sh root@95.81.101.148
```

---

## Контакты и поддержка

Если возникли проблемы:

1. Проверьте логи: `docker-compose logs -f claude-ml-trading`
2. Проверьте статус: `docker-compose ps`
3. Перезапустите сервис: `docker-compose restart`

Документация проекта:
- README.md - общее описание
- QUICKSTART.md - быстрый старт
- GIT_DEPLOY_GUIDE.md - детали деплоя через Git

---

**Последнее обновление:** 2026-07-28
**Версия системы:** 0.8.0 (Automated Deployment Ready)
