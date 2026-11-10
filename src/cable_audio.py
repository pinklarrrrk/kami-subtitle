import io
from pathlib import Path
import sys
import wave


def output_device():
    if "sounddevice" not in sys.modules:
        sys.path.insert(0, str(Path(__file__).with_name("vendor")))
    import sounddevice as sd

    return next((d["index"] for d in sd.query_devices()
                   if d["name"].startswith("CABLE Input")
                   and d["max_output_channels"] > 0
                   and sd.query_hostapis(d["hostapi"])["name"] == "Windows WASAPI"), None)


def install_driver():
    from hashlib import sha256
    from tempfile import TemporaryDirectory
    from urllib.request import urlopen
    from zipfile import ZipFile

    import win32event
    import win32process
    from win32com.shell import shell, shellcon

    url = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack46.zip"
    digest = "bc44e8974191a5a2427d6c979e2dab08dbb09925f3f435dfa2f0ba3e45b6eb90"
    with urlopen(url, timeout=20) as response:
        package = response.read(2 * 1024 * 1024)
    if sha256(package).hexdigest() != digest:
        raise RuntimeError("官方安装包校验失败")
    with TemporaryDirectory(prefix="kami-vbcable-") as folder:
        with ZipFile(io.BytesIO(package)) as archive:
            archive.extractall(folder)
        process = shell.ShellExecuteEx(
            fMask=shellcon.SEE_MASK_NOCLOSEPROCESS | shellcon.SEE_MASK_FLAG_DDEWAIT,
            lpVerb="runas", lpFile=str(Path(folder) / "VBCABLE_Setup_x64.exe"),
            lpDirectory=folder, nShow=1,
        )["hProcess"]
        try:
            win32event.WaitForSingleObject(process, win32event.INFINITE)
            code = win32process.GetExitCodeProcess(process)
            if code not in (0, 3010):
                raise RuntimeError(f"安装程序退出代码：{code}")
        finally:
            process.Close()


def play(wav):
    device = output_device()
    import sounddevice as sd

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
