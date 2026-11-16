"""Select the lyric line for a media playback position."""

from bisect import bisect_right
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import Lock
from time import monotonic
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import asyncio
import ctypes
import json
import msvcrt
import os
from pathlib import Path
import re
from ctypes import wintypes
from mambo import DATA

LYRICS_DIR = DATA / "bgm-lyrics"


TIMESTAMP = re.compile(r"\[(\d+):([0-5]\d)(?:[.:](\d{1,3}))?\]")
OFFSET = re.compile(r"\[offset\s*:\s*([+-]?\d+)\]", re.I)
LOG_EVENT = re.compile(r'^\[\d+:\d+:\d{4}/\d{6}:(\d+):.*?【playing】,(".*)$')
LOG_DECODE = bytes(((((v >> 4) ^ (((v & 15) + 8) & 15)) * 16
                     + (v >> 6) * 4 + (~(v >> 4) & 3)) & 255) for v in range(256))
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.GetTickCount64.restype = ctypes.c_uint64
open_shared = kernel.CreateFileW
open_shared.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
open_shared.restype = wintypes.HANDLE


@lru_cache(maxsize=1)
def netease_log(path, size, stamp):
    # Share read, write and delete so the player can keep writing or rotate its log.
    handle = open_shared(str(path), 0x80000000, 7, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        return None
    with os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY), "rb") as stream:
        stream.seek(max(0, size - 512 * 1024))
        tail = stream.read(512 * 1024).translate(LOG_DECODE).decode("utf-8", "replace")
    title, song_id, position, anchor = "", "", None, None
    now = kernel.GetTickCount64()
    for row in tail.splitlines():
        if "【playing】," not in row:
            continue
        match = LOG_EVENT.match(row)
        if not match or int(match[1]) > now:
            continue
        tick = int(match[1])
        name = match[2].split('"', 2)[1]
        if name not in ("playOneTrackInPlayingList", "setPlaying", "native播放资源load完成，开始播放",
                        "native播放state", "setPlayingPosition", "loadingSeek", "pause",
                        "resume", "stop playId=", "appRestore，播放信息恢复"):
            continue
        try:
            _, value, *extra = json.loads("[" + match[2] + "]")
            if name in ("playOneTrackInPlayingList", "setPlaying"):
                track = value["track"]
                if str(track["id"]) != song_id or name == "playOneTrackInPlayingList":
                    position, anchor = None, None
                title, song_id = track["name"], str(track["id"])
            elif name == "native播放资源load完成，开始播放" and str(value["songId"]) == song_id:
                position, anchor = 0, tick
            elif name == "appRestore，播放信息恢复" and str(value["id"]) == song_id:
                position, anchor = float(value["current"]), None if value.get("pause") else tick
            elif name in ("setPlayingPosition", "loadingSeek") and type(value) in (int, float) and 0 <= value <= 604800:
                position, anchor = value, tick if anchor is not None else None
            elif name in ("native播放state", "pause", "resume", "stop playId="):
                play_id = extra[0] if name == "native播放state" and extra else value
                if str(play_id).split("_", 1)[0] != song_id:
                    continue
                if name == "stop playId=":
                    position, anchor = None, None
                elif position is not None:
                    if anchor is not None:
                        position += max(0, tick - anchor) / 1000
                    anchor = tick if name == "resume" or (name == "native播放state" and value == 1) else None
        except (ValueError, KeyError, TypeError):
            continue
    return title, song_id, position, anchor


def netease_position(title, playing, paused):
    base = os.getenv("LOCALAPPDATA")
    if not base:
        return None, ""
    try:
        path = Path(base) / "NetEase/CloudMusic/cloudmusic.elog"
        info = path.stat()
        result = netease_log(path, info.st_size, info.st_mtime_ns)
    except OSError:
        return None, ""
    if not result or result[0].casefold().strip() != title.casefold().strip():
        return None, ""
    _, song_id, position, anchor = result
    if position is None or (anchor is not None) == paused:
        return None, song_id
    return position + ((kernel.GetTickCount64() - anchor) / 1000 if playing and anchor is not None else 0), song_id


class Lyrics:
    def __init__(self, text, translation=""):
        adjustment = OFFSET.search(text)
        offset = int(adjustment[1]) if adjustment else 0
        cues = {}
        for row in text.splitlines():
            matches = list(TIMESTAMP.finditer(row))
            if not matches:
                continue
            line = row[matches[-1].end():].strip()
            for tag in matches:
                minutes, seconds, fraction = tag.groups()
                when = (int(minutes) * 60 + int(seconds)) * 1000
                when += int((fraction or "").ljust(3, "0"))
                cues.setdefault(when + offset, []).append(line)
        # Blank cues mark instrumental breaks; keep highlighting the last sung line.
        self.times = sorted(t for t, lines in cues.items() if any(lines))
        self.lines = ["\n".join(dict.fromkeys(filter(None, cues[t]))) for t in self.times]
        self.translations = {}
        if translation:
            translated = Lyrics(translation)
            self.translations = dict(zip(translated.times, translated.lines))

    def at(self, seconds):
        index = bisect_right(self.times, seconds * 1000) - 1
        return self.lines[index] if index >= 0 else ""

    def window(self, seconds):
        if seconds is None or not self.times:
            return [], -1, [], []
        index = bisect_right(self.times, seconds * 1000) - 1
        lines, rows, times = [], [], []
        for slot in range(index - 1, index + 2):
            if 0 <= slot < len(self.lines):
                when = self.times[slot]
                lines.append(self.lines[slot])
                rows.append(self.translations.get(when, ""))
                times.append(when)
            else:
                lines.append("..." if slot == len(self.lines) else "")
                rows.append("")
                times.append(f"placeholder-{slot}")
        return lines, 1 if index >= 0 else -1, rows, times


@lru_cache(maxsize=64)
def online_lyrics(title, artist, song_id, period):
    if song_id.isascii() and song_id.isdecimal():
        try:
            url = "https://music.163.com/api/song/lyric?" + urlencode({"id": song_id, "lv": 1, "tv": 1})
            with urlopen(url, timeout=4) as response:
                data = json.load(response)
            lyrics = Lyrics(data.get("lrc", {}).get("lyric", ""),
                            data.get("tlyric", {}).get("lyric", ""))
            if lyrics.times:
                return lyrics
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    query = urlencode({"track_name": title, "artist_name": artist})
    request = Request("https://lrclib.net/api/search?" + query,
                      headers={"User-Agent": "KamiSubtitle (github.com/pinklarrrrk/kami-subtitle)"})
    def key(value):
        return " ".join(value.casefold().split())
    try:
        with urlopen(request, timeout=5) as response:
            matches = json.load(response)
        for match in matches:
            if (key(match["trackName"]) == key(title)
                    and key(match["artistName"]) == key(artist)
                    and match.get("syncedLyrics")):
                return Lyrics(match["syncedLyrics"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


_lookup = ThreadPoolExecutor(max_workers=1)
_lock = Lock()
_pending = None
_pending_key = None


def cached_online(title, artist, song_id):
    global _pending, _pending_key
    if not artist and not song_id:
        return None
    with _lock:
        if _pending and not _pending.done():
            return None
        key = (title, artist, song_id, int(monotonic() // 300))
        if _pending_key != key:
            _pending_key = key
            _pending = _lookup.submit(online_lyrics, *key)
            return None
        return _pending.result()


async def current_song():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status

    manager = await Manager.request_async()
    sessions = list(manager.get_sessions())
    sessions.sort(key=lambda session: "cloudmusic" not in session.source_app_user_model_id.lower())
    for session in sessions:
        playback = session.get_playback_info()
        if playback.playback_status not in (Status.PLAYING, Status.PAUSED):
            continue
        media = await session.try_get_media_properties_async()
        if not media or not media.title:
            continue
        timeline = session.get_timeline_properties()
        if timeline.last_updated_time.year <= 2000 and not timeline.end_time.total_seconds():
            seconds, song_id = (None, "")
            if "cloudmusic" in session.source_app_user_model_id.lower():
                seconds, song_id = netease_position(media.title, playback.playback_status == Status.PLAYING,
                                                    playback.playback_status == Status.PAUSED)
            return media.title, media.artist, seconds, song_id
        seconds = timeline.position.total_seconds()
        if playback.playback_status == Status.PLAYING and timeline.last_updated_time.year > 2000:
            elapsed = (datetime.now(timezone.utc) - timeline.last_updated_time).total_seconds()
            seconds += max(0, elapsed) * (playback.playback_rate or 1)
        end = timeline.end_time.total_seconds()
        return media.title, media.artist, min(seconds, end) if end > 0 else seconds, ""
    return "", "", 0, ""


def song_caption():
    title, artist, seconds, song_id = asyncio.run(current_song())
    lyrics = None
    for label in (f"{artist} - {title}", title) if title else ():
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", label).strip(" .") + ".lrc"
        try:
            data = (LYRICS_DIR / filename).read_bytes()
        except OSError:
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            text = data.decode("gb18030", errors="replace")
        lyrics = Lyrics(text)
        break
    if lyrics is None and title and seconds is not None:
        lyrics = cached_online(title, artist, song_id)
    lines, active, translations, times = lyrics.window(seconds) if lyrics else ([], -1, [], [])
    return {"title": title, "artist": artist, "lines": lines, "active": active,
            "translations": translations, "times": times,
            "lyric": lines[active] if active >= 0 else ""}
