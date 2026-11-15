"""عميل Bot API خفيف (stdlib فقط) — نفس الطريق المُجرَّب من الـ VM.

curl أثبت الوصول لـ api.telegram.org من هنا؛ urllib يفعل الشيء نفسه.
"""
import json
import time
import urllib.request
from pathlib import Path


class ApiError(Exception):
    pass


class BotApi:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"

    def _call(self, method: str, payload: dict, retries: int = 3):
        body = json.dumps(payload).encode()
        last = None
        for _ in range(retries):
            try:
                req = urllib.request.Request(
                    f"{self.base}/{method}", data=body,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    d = json.loads(r.read().decode())
                if d.get("ok"):
                    return d["result"]
                last = d
                if d.get("error_code") == 429:
                    time.sleep(d.get("parameters", {}).get("retry_after", 5))
                    continue
                raise ApiError(f"{method}: {d}")
            except ApiError:
                raise
            except Exception as e:
                last = e
                time.sleep(2)
        raise ApiError(f"{method} failed after retries: {last}")

    def send_message(self, chat_id, text, reply_markup=None):
        p = {"chat_id": chat_id, "text": text}
        if reply_markup:
            p["reply_markup"] = reply_markup
        return self._call("sendMessage", p)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        p = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup:
            p["reply_markup"] = reply_markup
        return self._call("editMessageText", p)

    def send_photo(self, chat_id, photo_path, caption, reply_markup=None):
        """إرسال صورة مع تعليق — multipart يدوي (stdlib فقط)."""
        import mimetypes
        import uuid
        boundary = uuid.uuid4().hex
        fields = {"chat_id": str(chat_id), "caption": caption}
        if reply_markup:
            fields["reply_markup"] = json.dumps(reply_markup)
        body = b""
        for k, v in fields.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                     f"name=\"{k}\"\r\n\r\n{v}\r\n").encode()
        fname = photo_path.name
        ctype = mimetypes.guess_type(fname)[0] or "image/png"
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f"name=\"photo\"; filename=\"{fname}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode()
        body += Path(photo_path).read_bytes()
        body += f"\r\n--{boundary}--\r\n".encode()
        last = None
        for _ in range(3):
            try:
                req = urllib.request.Request(
                    f"{self.base}/sendPhoto", data=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read().decode())
                if d.get("ok"):
                    return d["result"]
                last = d
            except Exception as e:
                last = e
                time.sleep(2)
        raise ApiError(f"sendPhoto failed: {last}")

    def edit_message_caption(self, chat_id, message_id, caption, reply_markup=None):
        p = {"chat_id": chat_id, "message_id": message_id, "caption": caption}
        if reply_markup:
            p["reply_markup"] = reply_markup
        return self._call("editMessageCaption", p)

    def get_updates(self, offset: int, timeout: int = 10):
        return self._call("getUpdates",
                          {"offset": offset, "timeout": timeout}, retries=1)

    def delete_webhook(self, drop_pending_updates: bool = True):
        """مسح الـ webhook + تفريغ طابور التحديثات العالق في تيليجرام."""
        return self._call("deleteWebhook",
                          {"drop_pending_updates": drop_pending_updates})

    def create_invite_link(self, chat_id, name: str):
        return self._call("createChatInviteLink",
                          {"chat_id": chat_id, "member_limit": 1, "name": name})

    def revoke_invite_link(self, chat_id, invite_link: str):
        return self._call("revokeChatInviteLink",
                          {"chat_id": chat_id, "invite_link": invite_link})

    def ban(self, chat_id, user_id):
        return self._call("banChatMember",
                          {"chat_id": chat_id, "user_id": user_id})

    def unban(self, chat_id, user_id):
        return self._call("unbanChatMember",
                          {"chat_id": chat_id, "user_id": user_id})

    def answer_callback(self, callback_query_id, text=None):
        p = {"callback_query_id": callback_query_id}
        if text:
            p["text"] = text
        return self._call("answerCallbackQuery", p)
