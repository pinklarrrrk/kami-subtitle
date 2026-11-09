import io
from pathlib import Path
import tempfile
import wave

import pythoncom
from win32com.client.dynamic import Dispatch

import mambo
import mimo_cloud
import voice_packs


SYSTEM = "系统朗读"
VOICE_FILE = mambo.DATA / "voice.txt"
AISHELL = "AISHELL-3"
SPEAKER_FILE = mambo.DATA / "aishell-speaker.txt"
SPEAKER_COUNT = 174


def aishell_speaker():
    try:
        sid = int(SPEAKER_FILE.read_text(encoding="utf-8"))
        return sid if 0 <= sid < SPEAKER_COUNT else 0
    except (OSError, ValueError):
        return 0


class SpeechError(RuntimeError):
    pass


def system_synthesize(text):
    with tempfile.TemporaryDirectory(prefix="kami-tts-") as folder:
        output = Path(folder) / "speech.wav"
        pythoncom.CoInitialize()
        try:
            voice = Dispatch("SAPI.SpVoice")
            if any("\u3400" <= char <= "\u9fff" for char in text):
                tokens = voice.GetVoices("Language=804")
                if not tokens.Count:
                    raise SpeechError("Windows 未安装简体中文语音，请在系统的语音设置中添加")
                voice.Voice = tokens.Item(0)
            stream = Dispatch("SAPI.SpFileStream")
            stream.Open(str(output), 3, False)
            try:
                voice.AudioOutputStream = stream
                voice.Speak(text, 16)  # Read literal text, including angle brackets.
            finally:
                stream.Close()
            audio = output.read_bytes()
            with wave.open(io.BytesIO(audio)) as wav:
                duration = wav.getnframes() / wav.getframerate()
        except (pythoncom.com_error, OSError, EOFError, wave.Error) as exc:
            raise SpeechError("系统朗读失败，请检查 Windows 语音设置") from exc
        finally:
            voice = stream = None
            pythoncom.CoUninitialize()
        if not duration:
            raise SpeechError("系统朗读没有生成声音")
        return audio, duration


def default_voice():
    return voice_packs.HUAYAN if voice_packs.installed(voice_packs.HUAYAN) else SYSTEM


def synthesize(text, voice=None, reference=None, transcript="", speaker=None):
    if voice is None:
        voice = default_voice()
    if voice == mimo_cloud.NAME:
        try:
            return mimo_cloud.synthesize(text)
        except mimo_cloud.MiMoError as exc:
            raise SpeechError(str(exc)) from exc
    if voice_packs.is_local_voice(voice):
        try:
            return voice_packs.synthesize(voice, text, (aishell_speaker() if speaker is None else speaker) if voice == AISHELL else 0)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SpeechError(f"{voice} 朗读失败，请检查语音包") from exc
    if voice != SYSTEM:
        return mambo.synthesize(text, reference, transcript)
    return system_synthesize(text)


def web_synthesize(text):
    try:
        voice = VOICE_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        voice = default_voice()
    if voice_packs.is_local_voice(voice):
        return synthesize(text, voice if voice_packs.installed(voice) else default_voice())
    if voice not in (SYSTEM, mimo_cloud.NAME) and not (mambo.locate() and (voice in ("曼波", "固定音色") or voice.startswith("自定义 "))):
        voice = default_voice()
    return synthesize(text, voice)
