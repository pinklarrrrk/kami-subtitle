"""Optional offline Japanese microphone recognition and translation."""

import audioop
from array import array
from contextlib import contextmanager
import json
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener

from mambo import DATA
from mic_caption import chdir


PACK = DATA / "japanese-captions"
MODEL = "HY-MT1.5-1.8B-Q4_K_M.gguf"
FILES = ("model.int8.onnx", "tokens.txt", "silero_vad.onnx", MODEL, "llama-server.exe")
RATE = 16000


def installed():
    return all((PACK / name).is_file() for name in FILES)


def load_models():
    import sherpa_onnx as sherpa

    with chdir(PACK):
        recognizer = sherpa.OfflineRecognizer.from_sense_voice(
            "model.int8.onnx", "tokens.txt", language="ja", use_itn=True, num_threads=2)
        config = sherpa.VadModelConfig()
        config.sample_rate = RATE
        config.silero_vad.model = "silero_vad.onnx"
        config.silero_vad.min_silence_duration = 0.45
        config.silero_vad.max_speech_duration = 8
        vad = sherpa.VoiceActivityDetector(config, buffer_size_in_seconds=20)
    return recognizer, vad, config.silero_vad.window_size


@contextmanager
def translator(stop):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    opener = build_opener(ProxyHandler({}))
    process = subprocess.Popen(
        [str(PACK / "llama-server.exe"), "-m", MODEL, "--host", "127.0.0.1",
         "--port", str(port), "-c", "1024", "-t", "3", "-ngl", "0", "--no-webui"],
        cwd=PACK, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        deadline = time.monotonic() + 90
        while not stop.is_set():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("无法启动离线翻译模型")
            try:
                with opener.open(base + "/health", timeout=1):
                    break
            except OSError:
                stop.wait(.25)

        def translate(text):
            prompt = "Translate the following Japanese segment into Simplified Chinese, without additional explanation.\n\n" + text
            data = {"messages": [{"role": "user", "content": prompt}],
                    "temperature": 0, "max_tokens": 128}
            request = Request(base + "/v1/chat/completions", json.dumps(data).encode(),
                              {"Content-Type": "application/json"})
            with opener.open(request, timeout=12) as response:
                translated = json.load(response)["choices"][0]["message"]["content"]
            return " ".join(translated.split())

        yield translate
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def decode(recognizer, samples):
    stream = recognizer.create_stream()
    stream.accept_waveform(RATE, samples)
    recognizer.decode_stream(stream)
    return " ".join(stream.result.text.split())


def recognize(stop, results):
    import sounddevice as sd

    pending = queue.Queue(maxsize=1)
    lock = threading.Lock()
    latest = 0

    def publish_translations(translate):
        while not stop.is_set():
            try:
                number, line = pending.get(timeout=.15)
            except queue.Empty:
                continue
            try:
                translated = translate(line)
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                if not stop.is_set():
                    results.put((stop, "notice", "离线翻译暂不可用，继续显示日文"))
                continue
            with lock:
                if translated and not stop.is_set() and number == latest:
                    results.put((stop, "text", line[:127] + "\n" + translated[:128]))

    try:
        if not installed():
            raise RuntimeError("尚未安装日语字幕包")
        recognizer, vad, window = load_models()
        device = sd.query_devices(kind="input")
        if "VB-Audio Virtual Cable" in device["name"]:
            raise RuntimeError("默认录音设备是虚拟线，请切换到实体麦克风")
        rate = int(device["default_samplerate"])
        remainder = array("h")
        state = None
        with translator(stop) as translate:
            if stop.is_set():
                return
            threading.Thread(target=publish_translations, args=(translate,), daemon=True).start()
            with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16") as mic:
                results.put((stop, "ready", "日语双语字幕已开启"))
                while not stop.is_set():
                    pcm, _ = mic.read(rate // 10)
                    pcm, state = audioop.ratecv(bytes(pcm), 2, 1, rate, RATE, state)
                    remainder.frombytes(pcm)
                    while len(remainder) >= window:
                        vad.accept_waveform([sample / 32768 for sample in remainder[:window]])
                        del remainder[:window]
                    while not vad.empty():
                        line = decode(recognizer, vad.front.samples)
                        vad.pop()
                        if not line:
                            continue
                        with lock:
                            latest += 1
                            results.put((stop, "text", line[:127]))
                            try:
                                pending.get_nowait()
                            except queue.Empty:
                                pass
                            pending.put_nowait((latest, line))
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        results.put((stop, "error", f"无法开启日语双语字幕：{error}"))
