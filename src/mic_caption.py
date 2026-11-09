from contextlib import chdir
import json
import os
from pathlib import Path
import sys


def recognize(stop, results):
    base = Path(__file__).parent
    vendor = str(base / "mic_vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    try:
        import sounddevice as sd
        from vosk import Model, KaldiRecognizer, SetLogLevel

        SetLogLevel(-1)
        model_path = base / "vosk-model-small-cn-0.22"
        if not model_path.is_dir():
            model_path = Path(os.environ["LOCALAPPDATA"]) / "MiMoReader" / model_path.name
        try:
            if str(model_path).isascii():
                model = Model(str(model_path))
            else:
                # Vosk's Windows model loader cannot open Unicode paths.
                with chdir(model_path.parent):
                    model = Model(model_path.name)
        except Exception:
            results.put((stop, "error", "无法加载离线识别模型，已回到打字朗读"))
            return
        if stop.is_set():
            return
        device = sd.query_devices(kind="input")
        if "VB-Audio Virtual Cable" in device["name"]:
            results.put((stop, "error", "默认录音设备是虚拟线，请在 Windows 选择实体麦克风"))
            return
        rate = int(device["default_samplerate"])
        recognizer = KaldiRecognizer(model, rate)
        last = ""
        with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16") as stream:
            results.put((stop, "ready", ""))
            while not stop.is_set():
                pcm, _ = stream.read(rate // 5)
                final = recognizer.AcceptWaveform(bytes(pcm))
                data = json.loads(recognizer.Result() if final else recognizer.PartialResult())
                line = data.get("text" if final else "partial", "").replace(" ", "")
                if line and (final or line != last):
                    results.put((stop, "text", line))
                last = "" if final else line
    except (ImportError, OSError, RuntimeError, ValueError):
        results.put((stop, "error", "无法开启麦克风字幕，请检查默认录音设备"))
