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
