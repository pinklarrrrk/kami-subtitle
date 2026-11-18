from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from pathlib import Path
from threading import Lock
from urllib.parse import unquote
import time
import webbrowser

from app import custom_font, subtitle_payload, subtitle_style
from bgm_lyrics import song_caption
from mambo import EngineError
from speech import SpeechError, web_synthesize

HOST = "127.0.0.1:8765"
ORIGIN = "http://" + HOST
caption = ("", 0)
preview_style = None
_bgm_lock = Lock()
_bgm_until = 0
_bgm_body = b"{}"
_bgm_cached_flags = None
bgm_enabled = (True, True)


def bgm_state():
    global _bgm_until, _bgm_body, _bgm_cached_flags
    with _bgm_lock:
        track, lyrics = bgm_enabled
        if not track and not lyrics:
            return b'{"showTrack":false,"showLyrics":false}'
        if (track, lyrics) != _bgm_cached_flags or time.monotonic() >= _bgm_until:
            try:
                state = song_caption(include_lyrics=lyrics)
            except (OSError, RuntimeError, ImportError):
                state = {}
            _bgm_body = json.dumps(dict(state, showTrack=track, showLyrics=lyrics), ensure_ascii=False).encode()
            _bgm_until = time.monotonic() + 0.25
            _bgm_cached_flags = (track, lyrics)
        return _bgm_body


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if sys.stderr is not None:
            super().log_message(format, *args)

    def reply(self, status, kind, data):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Host") != HOST:
            self.send_error(403)
            return
        if self.path in ("/", "/obs", "/preview", "/bgm"):
            page = {"/": "reader.html", "/bgm": "bgm.html"}.get(self.path, "obs.html")
            self.reply(200, "text/html; charset=utf-8", Path(__file__).with_name(page).read_bytes())
        elif self.path == "/bgm-state":
            self.reply(200, "application/json", bgm_state())
        elif self.path == "/fonts/SourceHanSansCN-Bold.otf":
            font = Path(__file__).parent / "fonts" / "SourceHanSansCN-Bold.otf"
            self.reply(200, "font/otf", font.read_bytes())
        elif self.path == "/subtitle-font":
            self.reply(200, "text/plain; charset=utf-8", subtitle_payload(subtitle_style())["font"].encode("ascii"))
        elif self.path in ("/subtitle-style", "/preview-style"):
            styles = (preview_style if self.path == "/preview-style" else None) or subtitle_style()
            self.reply(200, "application/json", json.dumps(subtitle_payload(styles)).encode())
        elif self.path.startswith("/custom-font/"):
            path = custom_font(unquote(self.path.removeprefix("/custom-font/")))
            if path:
                self.reply(200, "font/" + path.suffix.lower()[1:], path.read_bytes())
            else:
                self.send_error(404)
        elif self.path == "/caption":
            line, expiry = caption
            self.reply(200, "text/plain; charset=utf-8", (line if time.monotonic() < expiry else "").encode())
        else:
            self.send_error(404)

    def do_POST(self):
        global caption
        if self.headers.get("Host") != HOST or self.headers.get("Origin") != ORIGIN:
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                raise ValueError
            data = json.loads(self.rfile.read(size))
            line = data["text"]
            if not isinstance(line, str) or len(line) > 256:
                raise ValueError
            if self.path == "/caption":
                caption = (line, time.monotonic() + min(120, max(0, float(data["seconds"]))))
                self.reply(204, "text/plain", b"")
            elif self.path == "/speech":
                audio, _ = web_synthesize(line)
                self.reply(200, "audio/wav", audio)
            else:
                self.send_error(404)
        except (EngineError, SpeechError) as error:
            self.reply(502, "text/plain; charset=utf-8", str(error).encode())
        except (ValueError, KeyError, TypeError):
            self.reply(400, "text/plain; charset=utf-8", "请求或音频格式无效".encode())
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply(502, "text/plain; charset=utf-8", "无法获取朗读音频".encode())


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8765), Handler) as server:
        print("Kami: " + ORIGIN, flush=True)
        webbrowser.open(ORIGIN)
        server.serve_forever()
