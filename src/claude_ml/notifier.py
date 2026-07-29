from __future__ import annotations

import time

import requests
from requests import exceptions as requests_exceptions


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.session = requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    def _safe_error(self, method: str, err: BaseException) -> RuntimeError:
        return RuntimeError(f"Telegram request failed: {method}: {type(err).__name__}")

    def _request(self, method: str, *, params: dict | None = None, json_payload: dict | None = None, timeout: int = 20) -> dict:
        last_error = None
        for attempt in range(1, 4):
            try:
                if json_payload is not None:
                    response = self.session.post(
                        self._api_url(method),
                        json=json_payload,
                        timeout=timeout,
                    )
                else:
                    response = self.session.get(
                        self._api_url(method),
                        params=params,
                        timeout=timeout,
                    )
                response.raise_for_status()
                if not response.content:
                    return {}
                return response.json()
            except requests_exceptions.ReadTimeout as err:
                if method == "getUpdates":
                    return {"ok": True, "result": []}
                last_error = err
                if attempt < 3:
                    time.sleep(attempt * 2)
            except requests.RequestException as err:
                last_error = err
                if attempt < 3:
                    time.sleep(attempt * 2)
        if last_error:
            raise self._safe_error(method, last_error) from last_error
        raise RuntimeError(f"Telegram request failed: {method}")

    def send_message(self, text: str, chat_id: str | None = None, reply_markup: dict | None = None) -> None:
        target_chat = str(chat_id or self.chat_id).strip()
        if not self.bot_token or not target_chat:
            return
        payload = {"chat_id": target_chat, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self._request("sendMessage", json_payload=payload, timeout=20)

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> dict:
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        return self._request("getUpdates", params=params, timeout=timeout + 10)

    def notify_trade_entry(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        position_size: float,
        confidence: float,
        timestamp: str,
    ) -> None:
        """Send notification when a trade is opened."""
        emoji = "🟢" if side == "long" else "🔴"
        message = (
            f"{emoji} *НОВАЯ СДЕЛКА*\n\n"
            f"Символ: `{symbol}`\n"
            f"Направление: {side.upper()}\n"
            f"Цена входа: ${entry_price:,.2f}\n"
            f"Размер позиции: {position_size:.4f}\n"
            f"Уверенность: {confidence:.1f}%\n"
            f"Время входа: {timestamp[:19]}\n\n"
            f"Система будет следить за позицией и уведомит о выходе."
        )
        try:
            self.send_message(message)
        except Exception as e:
            print(f"Failed to send entry notification: {e}")

    def notify_trade_exit(
        self,
        symbol: str,
        side: str,
        exit_price: float,
        pnl_pct: float,
        pnl_usdt: float,
        exit_reason: str,
        timestamp: str,
    ) -> None:
        """Send notification when a trade is closed."""
        emoji = "✅" if pnl_pct >= 0 else "❌"
        pnl_sign = "+" if pnl_pct >= 0 else ""
        message = (
            f"{emoji} *СДЕЛКА ЗАКРЫТА*\n\n"
            f"Символ: `{symbol}`\n"
            f"Направление: {side.upper()}\n"
            f"Цена выхода: ${exit_price:,.2f}\n"
            f"PnL: `{pnl_sign}{pnl_pct:.2f}%` (${pnl_sign}{pnl_usdt:.2f})\n"
            f"Причина: {exit_reason}\n"
            f"Время выхода: {timestamp[:19]}\n\n"
            f"Ожидаю следующий сигнал..."
        )
        try:
            self.send_message(message)
        except Exception as e:
            print(f"Failed to send exit notification: {e}")
