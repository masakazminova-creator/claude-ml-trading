# 🚀 Быстрый старт - Деплой Claude ML Trading System

## Что было создано

В проекте настроена **полная автоматизация деплоя** на удалённый сервер. Теперь вы можете управлять проектом через Git и Docker.

### Созданные файлы:

1. **Dockerfile** - Образ контейнера для торгового бота
2. **docker-compose.yml** - Конфигурация запуска (бот + монитор)
3. **deploy.sh** - Скрипт автоматического деплоя на сервер
4. **.github/workflows/deploy.yml** - GitHub Actions для CI/CD
5. **CODE_SERVER.md** - Полная документация по настройке сервера

---

## Инструкция для первого развёртывания

### Шаг 1: Настройте Git репозиторий

```bash
cd C:\Bot\claude_ml_system

# Инициализируйте Git (если ещё не сделан)
git init
git add .
git commit -m "Initial commit: Claude ML with automated deployment"
```

### Шаг 2: Создайте репозиторий на GitHub

1. Зайдите на https://github.com/new
2. Создайте новый репозиторий (например, `claude-ml-trading`)
3. Скопируйте URL репозитория

```bash
# Добавьте remote
git remote add origin https://github.com/ВАШ_НИК/claude-ml-trading.git

# Запушьте код
git push -u origin main
```

### Шаг 3: Подготовьте сервер

Подключитесь к серверу и установите Docker:

```bash
ssh root@95.81.101.148

# Установите Docker
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | bash
usermod -aG docker $USER

# Установите Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Выйдите
exit
```

### Шаг 4: Создайте директорию проекта на сервере

```bash
ssh root@95.81.101.148

mkdir -p /opt/claude-ml-trading/{data,models,logs}
chown -R root:root /opt/claude-ml-trading

exit
```

### Шаг 5: Скопируйте .env файл на сервер

```bash
# Создайте .env файл на сервере
ssh root@95.81.101.148 "cat > /opt/claude-ml-trading/.env" < .env
```

### Шаг 6: Первый запуск

Запустите скрипт деплоя:

```bash
cd C:\Bot\claude_ml_system
./deploy.sh root@95.81.101.148
```

Скрипт автоматически:
- ✅ Закоммитит все изменения
- ✅ Запушит в Git
- ✅ Скопирует файлы на сервер
- ✅ Соберёт Docker образ
- ✅ Запустит контейнеры
- ✅ Покажет логи

---

## Как обновлять проект

### Автоматический способ (рекомендуется)

После любых изменений кода:

```bash
cd C:\Bot\claude_ml_system
./deploy.sh root@95.81.101.148
```

### Ручной способ (через Git)

```bash
# На локальном ПК
git add .
git commit -m "Описание изменений"
git push origin main

# На сервере (по SSH)
ssh root@95.81.101.148
cd /opt/claude-ml-trading
git pull
docker-compose build --no-cache
docker-compose up -d
```

---

## Полезные команды

### Проверка статуса

```bash
# На сервере
cd /opt/claude-ml-trading
docker-compose ps              # Статус контейнеров
docker-compose logs -f         # Логи в реальном времени
docker stats                   # Использование ресурсов
```

### Управление сервисами

```bash
docker-compose restart          # Перезапуск
docker-compose stop             # Остановка
docker-compose down             # Остановка и удаление контейнеров
docker-compose up -d            # Запуск
```

### Бэкапы

```bash
# Бэкап моделей
tar czf models-backup-$(date +%Y%m%d).tar.gz /opt/claude-ml-trading/models/

# Бэкап данных
tar czf data-backup-$(date +%Y%m%d).tar.gz /opt/claude-ml-trading/data/
```

---

## Что я могу делать удалённо

Теперь я могу:

✅ **Изменять код** - любые файлы проекта
✅ **Обновлять зависимости** - requirements.txt
✅ **Менять конфигурацию** - .env файл
✅ **Читать логи** - мониторинг работы
✅ **Запускать тесты** - проверка перед деплоем
✅ **Делать бэкапы** - модели и данные

Вы просто запускаете `./deploy.sh` после каждого обновления!

---

## Следующие шаги

1. **Протестируйте первый деплой** - запустите `./deploy.sh`
2. **Проверьте работу** - посмотрите логи на сервере
3. **Настройте уведомления** - добавьте Telegram bot token в .env
4. **Автоматизируйте полностью** - настройте GitHub Actions

---

**Готово!** Теперь ваш проект полностью автоматизирован для удалённого управления. 🎉
