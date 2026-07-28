# 🔐 Настройка GitHub Secrets для автоматического деплоя

## Что нужно сделать:

GitHub Actions нуждается в доступе к вашему серверу через SSH. Для этого нужно настроить secrets.

---

## Шаг 1: Создать SSH ключ на вашем локальном ПК (Windows)

Откройте PowerShell и выполните:

```powershell
# Создайте новый SSH ключ
ssh-keygen -t rsa -b 4096 -C "github-actions@claude-ml.com" -f $env:USERPROFILE\.ssh\github_actions_key -N ""

# Ключ создан, теперь покажите публичный ключ
cat $env:USERPROFILE\.ssh\github_actions_key.pub
```

Скопируйте **весь** вывод публичного ключа (начинается с `ssh-rsa`).

---

## Шаг 2: Добавить публичный ключ на сервер

Подключитесь к серверу:
```bash
ssh root@95.81.101.148
```

На сервере выполните:
```bash
# Вставьте ваш публичный ключ из буфера обмена
nano ~/.ssh/authorized_keys

# Вставьте скопированный ключ в новую строку
# Сохраните: Ctrl+O, Enter, Ctrl+X
```

Или одной командой (замените YOUR_PUBLIC_KEY на содержимое файла .pub):
```bash
echo "YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

## Шаг 3: Получить приватный ключ для GitHub

На вашем локальном ПК:
```powershell
# Покажите приватный ключ
cat $env:USERPROFILE\.ssh\github_actions_key
```

Скопируйте **весь** вывод (от `-----BEGIN RSA PRIVATE KEY-----` до `-----END RSA PRIVATE KEY-----`).

---

## Шаг 4: Добавить secrets в GitHub репозиторий

1. Зайдите на https://github.com/masakazminova-creator/claude-ml-trading
2. Перейдите в **Settings** → **Secrets and variables** → **Actions**
3. Нажмите **New repository secret**

Добавьте следующие secrets:

### Secret 1: SERVER_SSH_KEY
- **Name:** `SERVER_SSH_KEY`
- **Value:** Содержимое файла `$env:USERPROFILE\.ssh\github_actions_key` (приватный ключ)

### Secret 2: SERVER_HOST
- **Name:** `SERVER_HOST`
- **Value:** `95.81.101.148`

### Secret 3: SERVER_USER
- **Name:** `SERVER_USER`
- **Value:** `root`

---

## Шаг 5: Проверка настройки

После добавления secrets:

1. Зайдите в репозиторий на GitHub
2. Перейдите в **Actions**
3. Выберите workflow "🚀 Auto Deploy to Server"
4. Нажмите **Run workflow** → **Run workflow**

Workflow запустится и автоматически задеплоит код на сервер!

---

## Альтернатива: Использовать существующий SSH ключ

Если у вас уже есть SSH ключ для подключения к серверу, используйте его:

1. Скопируйте приватный ключ из `~/.ssh/id_rsa` (Linux/Mac) или `%USERPROFILE%\.ssh\id_rsa` (Windows)
2. Добавьте его как `SERVER_SSH_KEY` в GitHub secrets
3. Убедитесь что соответствующий публичный ключ есть в `~/.ssh/authorized_keys` на сервере

---

## Проверка работы

После настройки сделайте тестовый коммит:

```bash
cd C:\Bot\claude_ml_system
echo "# Test auto-deploy" >> README.md
git add README.md
git commit -m "test: Trigger auto-deploy workflow"
git push origin main
```

Зайдите на GitHub → Actions → увидите запускающийся workflow!

---

## Troubleshooting

### Ошибка: Permission denied (publickey)
- Проверьте что публичный ключ добавлен в `~/.ssh/authorized_keys` на сервере
- Проверьте права: `chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`

### Ошибка: Host key verification failed
- Workflow автоматически добавляет host key через ssh-keyscan
- Если проблема, добавьте вручную: `ssh-keyscan -H 95.81.101.148 >> ~/.ssh/known_hosts`

### Ошибка: Repository not found
- Проверьте что репозиторий существует
- Проверьте правильность URL в git remote

---

**Готово!** Теперь при каждом пуше на GitHub код будет автоматически тестироваться и деплоиться на сервер! 🚀
