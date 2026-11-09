import base64
import io
import json
import urllib.error
import urllib.request
import wave

import pywintypes
import win32crypt

import mambo


NAME = "小米 MiMo"
VOICES = ("冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean")
KEY_FILE = mambo.DATA / "mimo-key.dpapi"
VOICE_FILE = mambo.DATA / "mimo-preset.txt"
ENDPOINT = "https://api.xiaomimimo.com/v1/chat/completions"


class MiMoError(RuntimeError):
    pass


def save(key, voice):
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if key:
        try:
            encrypted = win32crypt.CryptProtectData(key.encode("utf-8"), NAME, None, None, None, 1)
        except pywintypes.error:
            raise OSError("无法加密 MiMo API Key") from None
        KEY_FILE.write_bytes(encrypted)
    else:
        KEY_FILE.unlink(missing_ok=True)
    VOICE_FILE.write_text(voice, encoding="utf-8")


def preset():
    try:
        value = VOICE_FILE.read_text(encoding="utf-8").strip()
        return value if value in VOICES else VOICES[0]
    except (OSError, UnicodeError):
        return VOICES[0]


def synthesize(text):
    try:
        key = win32crypt.CryptUnprotectData(KEY_FILE.read_bytes(), None, None, None, 1)[1].decode("utf-8")
    except (OSError, UnicodeError):
        raise MiMoError("请在「设置 → MiMo 设置」保存有效的 API Key") from None
    if not key:
        raise MiMoError("请先设置 MiMo API Key")
    request = urllib.request.Request(
        ENDPOINT,
        json.dumps({"model": "mimo-v2.5-tts", "messages": [{"role": "assistant", "content": text}],
                    "audio": {"format": "wav", "voice": preset()}}).encode("utf-8"),
        {"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        audio = base64.b64decode(result["choices"][0]["message"]["audio"]["data"], validate=True)
        with wave.open(io.BytesIO(audio), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        if duration <= 0:
            raise ValueError
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise MiMoError("MiMo 鉴权失败，请检查 API Key 和权限") from None
        raise MiMoError(f"MiMo 请求失败（HTTP {exc.code}）") from None
    except (OSError, TimeoutError):
        raise MiMoError("MiMo 连接失败，请检查网络") from None
    except (KeyError, ValueError, TypeError, IndexError, EOFError, wave.Error):
        raise MiMoError("MiMo 未返回可播放的音频") from None
    return audio, duration
