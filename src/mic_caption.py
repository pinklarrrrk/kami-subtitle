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


HOTWORD_FILE = Path(os.environ["LOCALAPPDATA"]) / "MiMoReader" / "asr-hotwords.txt"
DEFAULT_HOTWORDS = """OBS Studio
VTube Studio
Piper 华燕
咔咪字幕机
哔哩哔哩
哈基米
哈基米南北绿豆
曼波曼波
从从容容游刃有余
匆匆忙忙连滚带爬
不烧心文学
学知识不烧心
立规矩
生化摇
爱你老己
胆子真是肥嘟嘟的
我家猫会后空翻
我要验牌
弹幕姬
遇到难回答的问题又不说话了
又不说话了
三十年河东
三十年河西
莫欺少年穷
你这瓜保熟吗
这个我真绷不住了
我嘞个豆
这合理吗
你先别急
我就问你服不服
稳住我们能赢
别慌问题不大
你是懂直播的
这就是口碑
有内味了
直接给我看笑了
这波在大气层
听懂掌声
阁下又该如何应对
在绝对的实力面前
坏了冲我来的
你礼貌吗
这下不得不信了
差不多得了
不是哥们
给我整不会了
这个可以有
主包别急
主播说句话啊
"""


def hotword_text():
    try:
        return HOTWORD_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return DEFAULT_HOTWORDS


def save_hotwords(text):
    HOTWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOTWORD_FILE.write_text(text, encoding="utf-8")


def hotwords_for_stream():
    words = {}
    for line in hotword_text().splitlines():
        for phrase in re.split(r"[，。！？、；,.!?;/]+", line):
            phrase = " ".join(re.findall(r"[A-Za-z0-9\u3400-\u9fff]+", phrase.upper()))
            if phrase:
                words[phrase] = None
    return "/".join(words)


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
            modeling_unit="cjkchar+bpe", bpe_vocab="bpe.vocab", hotwords_score=1.5,
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
        hotwords = hotwords_for_stream()
        stream = recognizer.create_stream(hotwords or None)
        last = ""
        with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16") as mic:
            results.put((stop, "ready", ""))
            while not stop.is_set():
                pcm, _ = mic.read(rate // 10)
                samples = [sample / 32768.0 for sample in array("h", bytes(pcm))]
                line, endpoint = decode_chunk(recognizer, stream, rate, samples)
                if endpoint and not line:
                    line = last
                if line and (line != last or endpoint):
                    results.put((stop, "text", line))
                if line:
                    last = line
                if endpoint:
                    recognizer.reset(stream)
                    last = ""
    except (ImportError, OSError, RuntimeError, ValueError):
        results.put((stop, "error", "无法开启麦克风字幕，请检查默认录音设备"))
