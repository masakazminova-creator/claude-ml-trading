# Telegram Bot Setup Guide

## 🤖 Настройка Telegram уведомлений

### Шаг 1: Получить Chat ID

1. Откройте Telegram
2. Найдите бота `@userinfobot` 
3. Нажмите Start или отправьте любое сообщение
4. Бот покажет ваш Chat ID (например: `123456789`)

### Шаг 2: Настроить .env файл

Откройте `.env` и замените:

```env
# Было:
TELEGRAM_BOT_TOKEN=8845087233:AAHSOA7x6dN_BJ_KuNS7YuKkAUVwLHlaTug
TELEGRAM_CHAT_ID=your_chat_id_here

# Стало (замените на ваш реальный Chat ID):
TELEGRAM_BOT_TOKEN=8845087233:AAHSOA7x6dN_BJ_KuNS7YuKkAUVwLHlaTug
TELEGRAM_CHAT_ID=123456789
```

### Шаг 3: Запустить бота

```bash
cd C:\Bot\claude_ml_system
.venv\Scripts\activate
python scripts/run_telegram_bot.py
```

### Шаг 4: Протестировать

В Telegram найдите вашего бота по токену или отправьте команду:

```
/start
```

Бот ответит приветственным сообщением с доступными командами.

---

## 📱 Доступные команды

| Команда | Описание |
|---------|----------|
| `/start` | Приветственное сообщение |
| `/balance` | Текущий баланс, статистика, кнопка обновления |
| `/trades` | Последние 10 сделок |
| `/status` | Статус системы |

---

## 🔔 Автоматические уведомления

**Бот автоматически отправляет:**

### При входе в сделку:
```
🔔 NEW TRADE ENTRY

Symbol: BTCUSDT
Side: LONG
Entry Price: $50,125.50
Confidence: 82%
Position Size: 1.0%

Take Profit: $51,375.00
Stop Loss: $49,625.00
Trailing Stop: $49,375.00

Regime: trend_up
Reasoning: Early signal detected; Confirmation strong; Momentum aligned
```

### При выходе из сделки:
```
🟢 TRADE CLOSED

Symbol: BTCUSDT
Side: LONG
Entry Price: $50,125.50
Exit Price: $51,200.00
PnL: +2.14%

Exit Reason: Trailing Stop Hit
Highest Price: $51,250.00
Final Stop: $50,500.00
```

---

## 🎯 Кнопки в боте

### В сообщении /balance:
- **🔄 Обновить** - обновить баланс без ввода команды

---

## ⚠️ Troubleshooting

### Бот не отвечает:
1. Проверьте что бот запущен (`run_telegram_bot.py`)
2. Проверьте Chat ID в .env
3. Убедитесь что отправили `/start` боту

### Нет уведомлений о трейдах:
1. Проверьте TELEGRAM_BOT_TOKEN в .env
2. Проверьте TELEGRAM_CHAT_ID
3. Смотрите логи: `tail -f logs/telegram_bot.log`

### Ошибка "Chat not found":
- Отправьте `/start` вашему боту в Telegram
- Это активирует чат

---

## 🔐 Безопасность

**Никогда не публикуйте:**
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Эти данные должны быть только в `.env` файле!

---

**Готово!** Теперь вы будете получать все уведомления о трейдах прямо в Telegram! 🚀📱
