import io
from pathlib import Path
import sys
import wave


def play(wav):
    if "sounddevice" not in sys.modules:
        sys.path.insert(0, str(Path(__file__).with_name("vendor")))
    import sounddevice as sd

    device = next((d["index"] for d in sd.query_devices()
                   if d["name"].startswith("CABLE Input")
                   and d["max_output_channels"] > 0
                   and sd.query_hostapis(d["hostapi"])["name"] == "Windows WASAPI"), None)
    if device is None:
        raise RuntimeError("CABLE Input unavailable")
    with wave.open(io.BytesIO(wav)) as source:
        rate, channels = source.getframerate(), source.getnchannels()
        width = source.getsampwidth()
        samples = source.readframes(source.getnframes())
    dtype = ("uint8", "int16", "int24", "int32")[width - 1]
    offset = 0

    def callback(out, frames, timing, status):
        nonlocal offset
        chunk = samples[offset:offset + len(out)]
        offset += len(chunk)
        silence = b"\x80" if width == 1 else b"\x00"
        out[:] = chunk + silence * (len(out) - len(chunk))
        if offset >= len(samples):
            raise sd.CallbackStop

    stream = sd.RawOutputStream(device=device, samplerate=rate, channels=channels, dtype=dtype,
                                callback=callback, extra_settings=sd.WasapiSettings(auto_convert=True))
    try:
        stream.start()
    except Exception:
        stream.close()
        raise
    return stream
