# Git Auto-Deploy Guide

## 🚀 Настройка автоматического деплоя

### Первичная настройка (делать один раз)

```bash
# 1. На вашем ПК инициализируем Git
cd C:\Bot\claude_ml_system
git init
git add .
git commit -m "Initial commit"

# 2. Добавляем сервер как remote
git remote add production ssh://root@95.81.101.148/opt/git/claude_ml.git

# 3. Настраиваем сервер (выполнить на сервере)
ssh root@95.81.101.148
mkdir -p /opt/git/claude_ml.git
cd /opt/git/claude_ml.git
git init --bare
# Создать post-receive hook (см. инструкцию выше)
chmod +x hooks/post-receive
exit
```

---

## 📝 Рабочий процесс

### **Обычный деплой (одна команда):**

```bash
# На вашем ПК
cd C:\Bot\claude_ml_system
bash deploy.sh
```

**Что происходит:**
1. ✅ Все изменения коммитятся автоматически
2. ✅ Push на сервер
3. ✅ Post-receive hook автоматически:
   - Останавливает старые сервисы
   - Устанавливает зависимости
   - Деплоит новые файлы
   - Запускает обновлённые сервисы
   - Показывает статус и логи

---

### **Ручной режим (если нужно контролировать):**

```bash
# Коммит изменений
git add .
git commit -m "Your message"

# Push на сервер
git push production main

# Или другую ветку
git push production feature/new-feature
```

---

## 🔧 Настройка SSH ключей (опционально, чтобы не вводить пароль)

```bash
# На вашем ПК создаём SSH ключ
ssh-keygen -t ed25519 -C "your_email@example.com"

# Копируем публичный ключ на сервер
ssh-copy-id root@95.81.101.148

# Теперь git push не будет спрашивать пароль!
```

---

## 📊 Проверка статуса

```bash
# Посмотреть какие сервисы работают
ssh root@95.81.101.148 'supervisorctl status'

# Посмотреть логи
ssh root@95.81.101.148 'tail -f /opt/claude_ml_system/logs/runtime.log'

# Посмотреть историю деплоев
git log --oneline --graph
```

---

## ⚠️ Troubleshooting

### Ошибка "Remote rejected"
```bash
# Проверьте что remote настроен правильно
git remote -v

# Если нужно перенастроить
git remote remove production
git remote add production ssh://root@95.81.101.148/opt/git/claude_ml.git
```

### Ошибка "Permission denied"
```bash
# Настройте SSH ключи (см. выше)
# Или используйте пароль при каждом push
```

### Сервисы не запускаются после деплоя
```bash
# Подключитесь к серверу
ssh root@95.81.101.148

# Проверьте supervisor
supervisorctl status

# Перезапустите вручную
supervisorctl restart all

# Проверьте логи
tail -f /var/log/claude_ml.out.log
```

---

## 🎯 Best Practices

1. **Всегда тестируйте локально перед деплоем**
   ```bash
   python scripts/run_with_logging.py  # Проверить что работает
   ```

2. **Используйте осмысленные сообщения коммитов**
   ```bash
   git commit -m "Fix: trailing stop activation logic"
   ```

3. **Делайте небольшие изменения**
   - Легче откатить если что-то сломалось
   - Проще тестировать

4. **Следите за логами после деплоя**
   ```bash
   ssh root@95.81.101.148 'tail -f /opt/claude_ml_system/logs/*.log'
   ```

---

## 🔄 Откат изменений

Если что-то сломалось:

```bash
# Посмотреть предыдущие коммиты
git log --oneline

# Вернуться к рабочей версии
git checkout <working-commit-hash>

# Задеплоить старую версию
git push production HEAD:main
```

На сервере можно откатить файлы:
```bash
ssh root@95.81.101.148
cd /opt/git/claude_ml.git
git checkout <working-commit>
supervisorctl restart all
```

---

## 📈 Мониторинг

```bash
# Создать alias для удобства
echo 'alias claude-status="ssh root@95.81.101.148 '\''supervisorctl status'\''"' >> ~/.bashrc
echo 'alias claude-logs="ssh root@95.81.101.148 '\''tail -f /opt/claude_ml_system/logs/runtime.log'\''"' >> ~/.bashrc

# Теперь можно быстро проверять
claude-status
claude-logs
```

---

**Готово!** Теперь деплой одной командой: `bash deploy.sh` 🚀💰
