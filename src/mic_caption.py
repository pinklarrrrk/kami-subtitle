from array import array
from contextlib import chdir
import os
from pathlib import Path
import re
import sys

MODEL_DIR = "kami-asr-zh-en"
MODEL_FILES = (
    "tokens.txt",
    "encoder-epoch-99-avg-1.int8.onnx",
    "decoder-epoch-99-avg-1.onnx",
    "joiner-epoch-99-avg-1.int8.onnx",
)


def load_recognizer(model_path):
    from sherpa_onnx import OnlineRecognizer

    if not all((model_path / name).is_file() for name in MODEL_FILES):
        raise FileNotFoundError(model_path)
    # Some Windows native file readers require ASCII paths. Load synchronously
    # with relative paths, then restore the original working directory.
    with chdir(model_path):
        return OnlineRecognizer.from_transducer(
            *MODEL_FILES, num_threads=2, decoding_method="modified_beam_search",
            max_active_paths=4, enable_endpoint_detection=True,
            rule1_min_trailing_silence=1.6, rule2_min_trailing_silence=0.85,
            rule3_min_utterance_length=11.0,
        )


def caption_text(text):
    text = " ".join(text.split())
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[\u3400-\u9fff])", " ", text)
    return text


def decode_chunk(recognizer, stream, rate, samples):
    stream.accept_waveform(rate, samples)
    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)
    return caption_text(recognizer.get_result(stream)), recognizer.is_endpoint(stream)


def recognize(stop, results):
    base = Path(__file__).resolve().parent
    vendor = str(base / "mic_vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    model_path = base / MODEL_DIR
    if not model_path.is_dir():
        model_path = Path(os.environ.get("KAMI_ASR_MODEL", str(Path(os.environ["LOCALAPPDATA"]) / "MiMoReader" / MODEL_DIR)))
    try:
        recognizer = load_recognizer(model_path)
    except (ImportError, OSError, RuntimeError, ValueError):
        results.put((stop, "error", "无法加载离线中英识别模型，已回到打字朗读"))
        return
    if stop.is_set():
        return

    try:
        import sounddevice as sd

        device = sd.query_devices(kind="input")
        if "VB-Audio Virtual Cable" in device["name"]:
            results.put((stop, "error", "默认录音设备是虚拟线，请在 Windows 选择实体麦克风"))
            return
        rate = int(device["default_samplerate"])
        stream = recognizer.create_stream()
        last = ""
        with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16") as mic:
            results.put((stop, "ready", ""))
            while not stop.is_set():
                pcm, _ = mic.read(rate // 10)
                samples = [sample / 32768.0 for sample in array("h", bytes(pcm))]
                line, endpoint = decode_chunk(recognizer, stream, rate, samples)
                if line and (line != last or endpoint):
                    results.put((stop, "text", line))
                last = line
                if endpoint:
                    recognizer.reset(stream)
                    last = ""
    except (ImportError, OSError, RuntimeError, ValueError):
        results.put((stop, "error", "无法开启麦克风字幕，请检查默认录音设备"))
