import atexit
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave


class EngineError(RuntimeError):
    pass


HOST = "127.0.0.1"
PORT = 9880
URL = f"http://{HOST}:{PORT}"
DATA = Path(os.environ["LOCALAPPDATA"]) / "MiMoReader"
LOCATION = DATA / "mambo-pack.txt"
REF_TEXT = "大家好，欢迎来到我的频道，今天给大家分享一个有趣的内容"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
lock = threading.Lock()
process = None
closing = False


def engine_files(root):
    models = root / "models"
    for name in ("GPT-SoVITS", "GPT-SoVITS-v2pro-20250604"):
        engine = root / name
        files = (engine / "runtime/python.exe", engine / "api.py",
                 models / "manbo_e8_s168.pth", models / "manbo-e10.ckpt", models / "refer.wav")
        if all(path.is_file() for path in files):
            return files
    return None


def locate():
    try:
        value = LOCATION.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    root = Path(value)
    return root if value and root.is_absolute() and engine_files(root) else None


def ready():
    try:
        with opener.open(URL + "/openapi.json", timeout=1) as response:
            paths = json.load(response)["paths"]
            return "/" in paths and "/control" in paths
    except (OSError, ValueError, KeyError):
        return False


def ensure_engine():
    global process
    with lock:
        if closing:
            raise EngineError("曼波引擎已关闭")
        if process is not None and process.poll() is None and ready():
            return
        if process is None or process.poll() is not None:
            root = locate()
            if root is None:
                raise EngineError("请在设置中安装曼波语音包")
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex((HOST, PORT)) == 0:
                    raise EngineError("9880 端口被占用，无法启动曼波引擎")
            python, api, sovits, gpt, ref = engine_files(root)
            env = {**os.environ, "PYTHONUTF8": "1",
                   "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", "")}
            # A frozen app must not pass its bundled DLL search directory to the engine.
            if getattr(sys, "frozen", False):
                import ctypes
                ctypes.windll.kernel32.SetDllDirectoryW(None)
            try:
                DATA.mkdir(parents=True, exist_ok=True)
                with (DATA / "mambo-engine.log").open("wb") as log:
                    process = subprocess.Popen(
                        [str(python), "-u", str(api), "-a", HOST, "-p", str(PORT), "-s", str(sovits),
                         "-g", str(gpt), "-dr", str(ref), "-dt", REF_TEXT, "-dl", "zh"],
                        cwd=api.parent, env=env, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
            finally:
                if getattr(sys, "frozen", False):
                    ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
        for _ in range(180):
            if closing:
                raise EngineError("曼波引擎已关闭")
            if process.poll() is not None:
                raise EngineError("曼波引擎启动失败，请查看 mambo-engine.log")
            if ready():
                return
            time.sleep(.5)
        raise EngineError("曼波引擎启动超时，请稍后重试")


@atexit.register
def shutdown():
    global closing
    closing = True
    release()


def release():
    if process is not None and process.poll() is None:
        process.terminate()
        process.wait(timeout=5)


def synthesize(text, reference=None, transcript=""):
    ensure_engine()
    body = {"text": text, "text_language": "zh", "cut_punc": "，。？！；：、…,.;?!"}
    if reference is not None:
        body.update(refer_wav_path=str(reference), prompt_text=transcript, prompt_language="zh")
    request = urllib.request.Request(URL + "/", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=120) as response:
            audio = response.read()
        with wave.open(io.BytesIO(audio)) as wav:
            duration = wav.getnframes() / wav.getframerate()
        if duration <= 0:
            raise ValueError
    except (OSError, ValueError, EOFError, wave.Error) as exc:
        raise EngineError("曼波合成失败，请检查引擎日志或参考音频") from exc
    return audio, duration
