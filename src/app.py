import audioop
import base64
from array import array
from collections import deque
import ctypes
import io
import json
import os
from pathlib import Path
import queue
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinterdnd2 import DND_FILES, TkinterDnD
import tarfile
from tkinter import ttk, messagebox, filedialog, simpledialog, colorchooser
import urllib.request
from urllib.parse import quote
import webbrowser
import wave
import winsound
import zlib

import cable_audio
import mic_caption
import mambo
import mimo_cloud
import speech
import voice_packs


CAPTION = Path(os.environ["LOCALAPPDATA"]) / "MiMoReader" / "subtitle.txt"
FONT_FILE = CAPTION.with_name("subtitle-font.txt")
STYLE_FILE = CAPTION.with_name("subtitle-style.json")
CUSTOM_FONTS = CAPTION.with_name("subtitle-fonts")
FONTS = {"思源黑体": "source-han-sans", "思源宋体": "source-han-serif", "微软雅黑": "yahei"}


def subtitle_font():
    try:
        return FONTS.get(FONT_FILE.read_text(encoding="utf-8").strip(), "source-han-sans")
    except (OSError, UnicodeError):
        return "source-han-sans"


def subtitle_style():
    font = next(name for name, value in FONTS.items() if value == subtitle_font())
    defaults = {
        "mode": "气泡模式",
        "气泡模式": dict(font=font, size=0, color="#181818", background="#fffaf0", opacity=100, wrap=0),
        "字幕模式": dict(font=font, size=0, color="#ffffff", background="#000000", opacity=0,
                         outline=2, outline_color="#000000", wrap=0),
    }
    try:
        saved = json.loads(STYLE_FILE.read_text(encoding="utf-8"))
        if saved["mode"] in ("气泡模式", "字幕模式"):
            for mode in ("气泡模式", "字幕模式"):
                background = defaults[mode]["background"]
                for key in defaults[mode]:
                    fallback = 100 if key == "opacity" and saved[mode].get("background") else defaults[mode][key]
                    defaults[mode][key] = saved[mode].get(key, fallback)
                if not defaults[mode]["background"]:
                    defaults[mode].update(background=background, opacity=0)
            defaults["mode"] = saved["mode"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return defaults


def custom_font(name):
    if (not name or Path(name).name != name or ":" in name or
            Path(name).suffix.lower() not in (".ttf", ".otf", ".woff", ".woff2")):
        return None
    path = CUSTOM_FONTS / name
    return path if path.is_file() else None


def subtitle_payload(styles):
    mode = styles["mode"]
    active = styles[mode].copy()
    font = active["font"]
    path = custom_font(font) if font not in FONTS else None
    active["font"] = "custom" if path else FONTS.get(font, "source-han-sans")
    if path:
        active["font_url"] = "/custom-font/" + quote(path.name, safe="")
    active["mode"] = "bubble" if mode == "气泡模式" else "plain"
    if active["background"]:
        active["background"] += f'{round(active["opacity"] * 255 / 100):02x}'
    return active


VOICE_FILE = speech.VOICE_FILE
FIXED_VOICE = "固定音色"
FIXED_VOICE_FILE = VOICE_FILE.with_name("fixed-voice.wav")
VOICES = ("曼波",)


def segments(text):
    text = text.strip()
    if "\n" in text:
        for start in range(0, len(text), 256):
            part = text[start:start + 256].strip()
            if part:
                yield part
        return
    for sentence in re.split(r"(?<=[。！？!?；;])|\n+", text):
        sentence = sentence.strip()
        while len(sentence) > 48:
            cut = max(sentence.rfind(mark, 12, 48) for mark in "，、, ")
            cut = cut + 1 if cut >= 0 else 48
            yield sentence[:cut].strip()
            sentence = sentence[cut:].strip()
        if sentence:
            yield sentence


def change_speed(audio, speed):
    with wave.open(io.BytesIO(audio)) as wav:
        channels, width, rate, frames, *_ = wav.getparams()
        pcm = wav.readframes(frames)
    if width == 1:
        pcm = audioop.bias(pcm, 1, -128)
    samples = array("h", audioop.lin2lin(pcm, width, 2))
    mono = (audioop.tomono(samples.tobytes(), 2, .5, .5) if channels == 2
            else samples[::channels].tobytes())
    overlap = max(1, rate // 100)
    hop = overlap * 2
    length = max(1, round(frames / speed))
    output = samples[:min(hop + overlap, length) * channels]
    for pos in range(hop, length, hop):
        expected = round(pos * speed)
        count = min(hop + overlap, length - pos)
        last_start = max(0, frames - count)
        start = max(0, min(expected - overlap // 2, last_start))
        last_match = min(expected + overlap // 2, last_start)
        blend = min(overlap, len(output) // channels - pos, length - pos)
        if blend > 0 and last_match > start:
            block = output[pos * channels:(pos + blend) * channels]
            reference = audioop.tomono(block.tobytes(), 2, .5, .5) if channels == 2 else block[::channels].tobytes()
            if audioop.rms(reference, 2):
                def match(index):
                    candidate = mono[index * 2:(index + blend) * 2]
                    return audioop.findfactor(candidate, reference) / max(1, audioop.rms(candidate, 2))

                start = max(range(start, last_match + 1, 2), key=match)
        if blend > 0 and start + blend <= frames:
            for i in range(blend):
                for channel in range(channels):
                    dst = (pos + i) * channels + channel
                    src = (start + i) * channels + channel
                    output[dst] = round((output[dst] * (blend - i) + samples[src] * i) / blend)
        tail = samples[(start + blend) * channels:(start + count) * channels]
        output.extend(tail)
        output.extend(array("h", [0]) * ((pos + count) * channels - len(output)))
    result = io.BytesIO()
    with wave.open(result, "wb") as wav:
        wav.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(output.tobytes())
    return result.getvalue(), len(output) / channels / rate


def rounded_surface(size, radius, fill, border):
    fill, border = (bytes.fromhex(color[1:]) for color in (fill, border))
    offsets = (0.125, 0.375, 0.625, 0.875)
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            inside = inner = 0
            for sy in offsets:
                for sx in offsets:
                    px, py = x + sx, y + sy
                    dx = max(radius - px, px - (size - radius), 0)
                    dy = max(radius - py, py - (size - radius), 0)
                    distance = dx * dx + dy * dy
                    inside += distance <= radius * radius
                    inner += distance <= (radius - 1) ** 2 and 1 <= px <= size - 1 and 1 <= py <= size - 1
            rows.extend(round((f * inner + b * (inside - inner)) / inside) if inside else 0
                        for f, b in zip(fill, border))
            rows.append(round(255 * inside / 16))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return tk.PhotoImage(data=base64.b64encode(png), format="png")


def modern_styles(style):
    images = []
    for name, colors in {
        "Soft": (("#ffffff", "#dce5eb"), ("#eaf2f5", "#c8d9df"), ("#e6eef2", "#b9cdd4"), ("#f4f7f9", "#e6edf1")),
        "Accent": (("#176f64", "#176f64"), ("#125d54", "#125d54"), ("#0e5149", "#0e5149"), ("#e3ebe9", "#e3ebe9")),
    }.items():
        normal, hover, pressed, disabled = (rounded_surface(30, 2, *pair) for pair in colors)
        images.extend((normal, hover, pressed, disabled))
        element = name + ".surface"
        style.element_create(element, "image", normal, ("disabled", disabled), ("pressed", pressed),
                             ("active", hover), border=3, padding=0, sticky="nsew")
        button = name + ".TButton"
        style.layout(button, [(element, {"sticky": "nsew", "children": [
            ("Button.focus", {"sticky": "nsew", "children": [
                ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})
            ]})
        ]})])
        style.configure(button, padding=(7, 5), width=0, foreground="#ffffff" if name == "Accent" else "#263a4b")
        style.map(button, foreground=[("disabled", "#7a8994")], background=[("disabled", "#f4f6fa")])
        if name == "Soft":
            style.layout("TButton", style.layout(button))
            style.configure("TButton", padding=(7, 5), width=0)
    surface = rounded_surface(24, 2, "#ffffff", "#dce5eb")
    images.append(surface)
    style.element_create("Editor.surface", "image", surface, border=3, padding=0, sticky="nsew")
    style.layout("Editor.TFrame", [("Editor.surface", {"sticky": "nsew"})])
    thumb = rounded_surface(16, 8, "#176f64", "#176f64")
    track = rounded_surface(10, 4, "#e6edf1", "#e6edf1")
    images.extend((thumb, track))
    style.element_create("Kami.Scale.slider", "image", thumb)
    style.element_create("Kami.Scale.trough", "image", track, border=4, sticky="we")
    style.layout("Kami.Horizontal.TScale", [
        ("Kami.Scale.trough", {"sticky": "we", "children": [
            ("Kami.Scale.slider", {"side": "left", "sticky": ""})
        ]})
    ])
    style.configure("Kami.Horizontal.TScale", troughcolor="#e6edf1", borderwidth=0, background="#ffffff")
    return images


def integer_slider(parent, variable, low, high, length=170):
    slider = ttk.Scale(parent, from_=low, to=high, length=length, style="Kami.Horizontal.TScale")
    slider.set(int(variable.get()))
    slider.configure(command=lambda value: variable.set(str(round(float(value)))))
    return slider


class Reader:
    def __init__(self, root, folder):
        self.root = root
        self.wav = Path(folder) / "speech.wav"
        self.results = queue.Queue()
        self.prefetching = False
        self.prefetched = None
        self.mic_results = queue.Queue()
        self.mic_stop = None
        self.mic_owns_caption = False
        self.generation = 0
        self.timer = None
        self.caption_timer = None
        self.restart_requested = False
        self.stream = None
        self.previous = None
        self.submitted = None
        self.jobs = deque()
        self.busy = False
        self.recording = []
        self.write_caption("")
        root.title("咔咪字幕机")
        assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
        icon = str(assets / "kami.ico")
        self.window_icon = icon
        root.iconbitmap(icon)
        root.geometry(f"380x285+{max(0, root.winfo_screenwidth() - 420)}+80")
        root.minsize(360, 255)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 9), background="#f4f6fa", foreground="#17243b")

        self.style_images = modern_styles(style)
        style.configure("Muted.TLabel", foreground="#657687")
        panel = ttk.Frame(root, padding=12)
        panel.pack(fill="both", expand=True)
        style.configure("CardTitle.TLabel", background="#ffffff", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Card.TLabel", background="#ffffff")
        style.configure("Card.TCheckbutton", background="#ffffff")
        style.configure("Card.Soft.TButton", background="#ffffff")
        style.map("Card.Soft.TButton", background=[("disabled", "#ffffff")])
        self.settings_window = tk.Toplevel(root, background="#f4f6fa")
        self.settings_window.withdraw()
        self.settings_window.title("咔咪字幕机 · 设置")
        self.settings_window.iconbitmap(icon)
        self.settings_window.minsize(400, 280)
        self.settings_window.protocol("WM_DELETE_WINDOW", self.settings_window.withdraw)
        cards = ttk.Frame(self.settings_window, padding=14)
        cards.pack(fill="both", expand=True)

        def card(title):
            surface = ttk.Frame(cards, style="Editor.TFrame")
            surface.pack(fill="x", pady=(0, 9))
            frame = ttk.Frame(surface, style="Card.TFrame")
            frame.pack(fill="both", expand=True, padx=13, pady=10)
            ttk.Label(frame, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
            return frame

        voice_card = card("朗读")
        voice_row = ttk.Frame(voice_card, style="Card.TFrame")
        voice_row.pack(fill="x")
        ttk.Label(voice_row, text="音色", style="Card.TLabel").pack(side="left", padx=(0, 8))
        try:
            saved_voice = voice_packs.resolve_voice(VOICE_FILE.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeError):
            saved_voice = speech.default_voice()
        self.slot_names = {}
        for slot in range(1, 5):
            try:
                self.slot_names[slot] = VOICE_FILE.with_name(f"voice-{slot}.txt").read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                self.slot_names[slot] = ""
        voices = self.voice_options()
        self.voice = tk.StringVar(value=saved_voice if saved_voice in voices else speech.default_voice())
        style.configure("Card.TCombobox", padding=(6, 4))
        style.map("Card.TCombobox", fieldbackground=[("readonly", "#ffffff")])
        self.picker = ttk.Combobox(voice_row, textvariable=self.voice, values=voices, state="readonly", style="Card.TCombobox")
        self.picker.pack(side="left", fill="x", expand=True)
        self.picker.bind("<<ComboboxSelected>>", self.save_voice)
        self.speaker_button = ttk.Button(voice_row, text="切换音色…", style="Card.Soft.TButton", command=self.choose_aishell_speaker)
        self.rename_button = ttk.Button(voice_row, text="重命名", width=7, style="Card.Soft.TButton", command=self.rename_slot)
        self.vts = tk.BooleanVar(value=False)
        speed_row = ttk.Frame(voice_card, style="Card.TFrame")
        speed_row.pack(fill="x", pady=(4, 0))
        ttk.Label(speed_row, text="语速", style="Card.TLabel").pack(side="left", padx=(0, 8))
        self.speed = tk.DoubleVar(value=1.0)
        rate = ttk.Label(speed_row, text="1.0×", width=5, anchor="e", style="Card.TLabel")
        rate.pack(side="right")
        speed_slider = ttk.Scale(speed_row, from_=6, to=16, orient="horizontal", style="Kami.Horizontal.TScale")
        speed_slider.set(10)

        def set_speed(value):
            step = round(float(value))
            if abs(speed_slider.get() - step) > 1e-6:
                speed_slider.set(step)
            self.speed.set(step / 10)
            rate.configure(text=f"{step / 10:.1f}×")

        speed_slider.configure(command=set_speed)
        speed_slider.pack(side="left", fill="x", expand=True)
        voice_actions = ttk.Frame(voice_card, style="Card.TFrame")
        voice_actions.pack(fill="x", pady=(6, 0))
        ttk.Button(voice_actions, text="语音包…", style="Card.Soft.TButton", command=self.manage_packs).pack(side="left")
        ttk.Button(voice_actions, text="MiMo 设置…", style="Card.Soft.TButton", command=self.configure_mimo).pack(side="left", padx=(6, 0))
        ttk.Button(voice_actions, text="识别热词…", style="Card.Soft.TButton", command=self.edit_hotwords).pack(side="left", padx=(6, 0))
        output_card = card("字幕与输出")
        ttk.Button(output_card, text="字幕样式…", style="Card.Soft.TButton", command=self.edit_subtitle_style).pack(side="left")
        ttk.Checkbutton(output_card, text="送到 VTS", variable=self.vts, style="Card.TCheckbutton").pack(side="left", padx=(12, 0))
        app_card = card("窗口")
        pin = tk.BooleanVar(value=True)
        ttk.Checkbutton(app_card, text="主窗口置顶", variable=pin, style="Card.TCheckbutton",
                        command=lambda: root.attributes("-topmost", pin.get())).pack(side="left")
        ttk.Button(app_card, text="关于 · 问题反馈", style="Card.Soft.TButton", command=self.show_about).pack(side="right")
        self.queue_panel = ttk.Frame(panel)
        self.queue_empty = ttk.Label(self.queue_panel, text="队列为空", style="Muted.TLabel")
        self.queue_empty.pack(anchor="w", padx=2)
        self.queue_view = tk.Listbox(self.queue_panel, height=3, takefocus=False, activestyle="none",
                                     borderwidth=0, highlightthickness=0, background="#f4f6fa", foreground="#17243b",
                                     font=("Microsoft YaHei UI", 9))
        self.queue_scroll = ttk.Scrollbar(self.queue_panel, command=self.queue_view.yview)
        self.queue_view.configure(yscrollcommand=self.queue_scroll.set)
        editor = ttk.Frame(panel, style="Editor.TFrame")
        self.input = tk.Text(editor, wrap="word", undo=True, font=("Microsoft YaHei UI", 11),
                             background="#ffffff", foreground="#17243b", relief="flat", borderwidth=0,
                             highlightthickness=0, padx=6, pady=4, insertbackground="#17243b")
        self.status = tk.StringVar(value=f"{self.voice.get()} · 回车朗读")
        ttk.Label(panel, textvariable=self.status, style="Muted.TLabel").pack(side="bottom", fill="x", pady=(4, 0))
        footer = ttk.Frame(panel)
        footer.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(footer, text="重启", width=6, style="Soft.TButton", command=lambda: self.close(restart=True)).pack(side="right")
        ttk.Button(footer, text="设置…", width=8, style="Soft.TButton", command=self.open_settings).pack(side="left")
        self.mic_button = ttk.Button(footer, text="开麦字幕", style="Soft.TButton", command=self.toggle_mic)
        self.mic_button.pack(side="left", padx=(6, 0))
        controls = ttk.Frame(panel)
        controls.pack(side="bottom", fill="x")
        ttk.Button(controls, text="朗读", style="Accent.TButton", command=self.start).pack(side="left")
        ttk.Button(controls, text="停止", style="Soft.TButton", command=self.stop).pack(side="left", padx=5)
        self.replay_button = ttk.Button(controls, text="重播上条", style="Soft.TButton", command=self.replay, state="disabled")
        self.replay_button.pack(side="left")
        self.obs_button = ttk.Button(controls, text="OBS 字幕地址", style="Soft.TButton", command=self.copy_path)
        self.obs_button.pack(side="right")
        self.copy_hint = tk.Label(panel, text="已复制", background="#e3f1ee", foreground="#16695f", padx=9, pady=3)
        self.copy_hint_timer = None
        self.queue_panel.pack(fill="x", pady=(4, 0))
        editor.pack(fill="both", expand=True, pady=(5, 8))
        self.input.pack(fill="both", expand=True, padx=7, pady=7)
        self.show_description()
        self.input.focus_set()
        self.input.bind("<Shift-Return>", self.insert_line_break)
        self.input.bind("<Return>", self.start)
        self.input.bind("<KP_Enter>", self.start)
        root.bind("<Return>", self.enter_to_read)
        root.bind("<KP_Enter>", self.enter_to_read)
        root.bind("<Escape>", lambda _: self.stop())
        root.after(40, self.poll)

    def insert_line_break(self, event):
        self.input.insert("insert", "\n")
        return "break"

    def enter_to_read(self, event):
        return self.start(event)

    def toggle_mic(self):
        if self.mic_stop is not None:
            self.mic_stop.set()
            self.mic_stop = None
            self.mic_button.configure(text="开麦字幕")
            if self.mic_owns_caption:
                self.write_caption("")
                self.mic_owns_caption = False
            self.status.set("已切回打字朗读")
            return
        self.mic_stop = threading.Event()
        self.mic_button.configure(text="关麦 · 打字")
        self.status.set("正在启动麦克风字幕…")
        threading.Thread(target=mic_caption.recognize, args=(self.mic_stop, self.mic_results), daemon=True).start()

    def poll_mic(self):
        while True:
            try:
                stop, kind, text = self.mic_results.get_nowait()
            except queue.Empty:
                return
            if stop is not self.mic_stop:
                continue
            if kind == "error":
                self.toggle_mic()
                self.status.set(text)
            elif kind == "ready" and not self.busy:
                self.status.set("麦克风字幕已开启")
            elif kind == "text" and not self.busy and (self.caption_timer is None or self.mic_owns_caption):
                try:
                    self.write_caption(text, min(6, max(1.8, len(text) * .15)))
                    self.mic_owns_caption = True
                except OSError:
                    self.status.set("无法更新 OBS 字幕")

    def open_settings(self):
        if self.settings_window.state() == "withdrawn" and not self.settings_window.winfo_ismapped():
            self.settings_window.update_idletasks()
            x = max(0, self.root.winfo_x() - self.settings_window.winfo_reqwidth() - 16)
            self.settings_window.geometry(f"+{x}+{max(0, self.root.winfo_y())}")
        self.settings_window.deiconify()
        self.settings_window.lift()
        self.settings_window.focus_set()

    def settings_parent(self):
        return self.root if self.settings_window.state() == "withdrawn" else self.settings_window

    def write_caption(self, text, seconds=0):
        from web import ORIGIN

        if self.caption_timer is not None:
            self.root.after_cancel(self.caption_timer)
            self.caption_timer = None
        CAPTION.parent.mkdir(parents=True, exist_ok=True)
        CAPTION.write_text(text, encoding="utf-8-sig")
        request = urllib.request.Request(
            ORIGIN + "/caption", json.dumps({"text": text, "seconds": seconds}).encode(),
            {"Origin": ORIGIN, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=1):
            pass
        if text:
            self.caption_timer = self.root.after(round(seconds * 1000), self.write_caption, "")

    def copy_path(self):
        from web import ORIGIN

        self.root.clipboard_clear()
        self.root.clipboard_append(ORIGIN + "/obs")
        if self.copy_hint_timer is not None:
            self.root.after_cancel(self.copy_hint_timer)
        panel = self.copy_hint.master
        self.copy_hint.place(x=self.obs_button.winfo_rootx() - panel.winfo_rootx() + self.obs_button.winfo_width(),
                             y=self.obs_button.winfo_rooty() - panel.winfo_rooty() - 4, anchor="se")
        self.copy_hint.lift()
        self.copy_hint_timer = self.root.after(1400, self.hide_copy_hint)

    def hide_copy_hint(self):
        self.copy_hint.place_forget()
        self.copy_hint_timer = None

    def new_dialog(self, parent):
        dialog = tk.Toplevel(parent)
        dialog.iconbitmap(self.window_icon)
        return dialog

    def show_about(self):
        version = "v1.0.6"
        dialog = self.new_dialog(self.settings_parent())
        dialog.title("关于咔咪字幕机")
        dialog.transient(self.settings_parent())
        panel = ttk.Frame(dialog, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text=f"咔咪字幕机 {version}").pack(anchor="w")
        ttk.Label(panel, justify="left", wraplength=390, text=(
            "本软件采用 Vibe Coding 方式开发，由用户提出需求并迭代，AI 协助编写代码。\n\n"
            "开源致谢：Zipformer（中英语音识别）、python-sounddevice（音频采集）、"
            "思源黑体（字幕字体）、Python 与 Tcl/Tk（桌面界面）。感谢 sherpa-onnx、Piper 华燕、Matcha Baker / Vocos，以及 MamboTTS 与 GPT-SoVITS 提供本地语音合成。\n\n"
            "原创代码采用 MIT；原创说明文字和标志采用 CC BY 4.0。第三方组件遵循各自的许可。\n\n"
            "反馈邮箱：pinklark@qq.com\n可复制下方模板，填写后发邮件。"
        )).pack(anchor="w", pady=8)

        def copy_feedback():
            dialog.clipboard_clear()
            dialog.clipboard_append(f"收件人：pinklark@qq.com\n主题：咔咪字幕机 · 问题反馈\n问题描述：\n复现步骤：\n实际结果：\n预期结果：\n咔咪字幕机版本：{version}\nWindows / OBS 版本：")
            feedback.configure(text="已复制反馈模板")

        feedback = ttk.Button(panel, text="复制反馈模板", command=copy_feedback)
        feedback.pack(anchor="w")

    def edit_subtitle_style(self):
        import web

        styles = subtitle_style()
        dialog = self.new_dialog(self.settings_parent())
        dialog.title("字幕样式")
        dialog.transient(self.settings_parent())
        dialog.resizable(False, False)
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=12)
        panel.pack(fill="both", expand=True)
        mode = tk.StringVar(dialog, styles["mode"])
        picker = ttk.Combobox(panel, textvariable=mode, values=("气泡模式", "字幕模式"), state="readonly")
        picker.pack(fill="x")
        fields = ttk.Frame(panel)
        fields.pack(fill="x", pady=8)
        values = {
            name: {key: tk.StringVar(dialog, value) for key, value in styles[name].items()}
            for name in ("气泡模式", "字幕模式")
        }
        limits = {"size": (0, 160), "outline": (0, 12), "opacity": (0, 100), "wrap": (0, 60)}

        def current():
            draft = {"mode": mode.get()}
            for name, options in values.items():
                draft[name] = {}
                for key, var in options.items():
                    value = var.get()
                    if key in limits:
                        lo, hi = limits[key]
                        value = int(value)
                        if not lo <= value <= hi:
                            raise ValueError(f"{name}：数值应在 {lo} 到 {hi} 之间。")
                    draft[name][key] = value
            return draft

        def update_preview(*args):
            try:
                web.preview_style = current()
            except ValueError:
                pass

        def add_font(var):
            filename = filedialog.askopenfilename(parent=dialog, title="导入字幕字体",
                filetypes=[("字体文件", "*.ttf *.otf *.woff *.woff2")])
            if not filename:
                return
            source = Path(filename)
            if source.suffix.lower() not in (".ttf", ".otf", ".woff", ".woff2"):
                return
            try:
                CUSTOM_FONTS.mkdir(parents=True, exist_ok=True)
                target = CUSTOM_FONTS / source.name
                if source.resolve() != target.resolve():
                    shutil.copyfile(source, target)
            except OSError as exc:
                messagebox.showerror("无法导入字体", str(exc), parent=dialog)
                return
            var.set(target.name)
            render()

        def render(event=None):
            for widget in fields.winfo_children():
                widget.destroy()
            options = values[mode.get()]
            labels = {"font": "字体", "size": "字号（0 为自动）", "color": "文字颜色",
                      "background": "底色", "outline": "外描边（像素）",
                      "opacity": "底色不透明度（%）", "outline_color": "描边颜色", "wrap": "换行字数（0 为自动）"}
            for row, (key, var) in enumerate(options.items()):
                ttk.Label(fields, text=labels[key]).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
                if key == "font":
                    fonts = sorted(path.name for path in CUSTOM_FONTS.glob("*") if custom_font(path.name))
                    widget = ttk.Combobox(fields, textvariable=var, values=(*FONTS, *fonts), state="readonly", width=17)
                    ttk.Button(fields, text="添加字体…", command=lambda target=var: add_font(target)).grid(row=row, column=2)
                elif key in ("color", "background", "outline_color"):
                    widget = ttk.Button(fields, text=var.get() or "选择颜色…")

                    def set_color(color, target=var, button=widget):
                        target.set(color)
                        button.configure(text=color or "选择颜色…")

                    def choose(target=var, apply=set_color):
                        _, color = colorchooser.askcolor(target.get() or "#ffffff", parent=dialog)
                        if color:
                            apply(color)
                    widget.configure(command=choose)
                else:
                    lo, hi = limits[key]
                    widget = integer_slider(fields, var, lo, hi)
                    ttk.Label(fields, textvariable=var, width=4, anchor="e").grid(row=row, column=2, sticky="e")
                widget.grid(row=row, column=1, sticky="ew")

        def save():
            try:
                STYLE_FILE.write_text(json.dumps(current(), ensure_ascii=False), encoding="utf-8")
            except (ValueError, OSError) as exc:
                messagebox.showerror("无法保存字幕样式", str(exc), parent=dialog)
                return
            dialog.destroy()

        for var in (mode, *(var for options in values.values() for var in options.values())):
            var.trace_add("write", update_preview)
        dialog.bind("<Destroy>", lambda event: setattr(web, "preview_style", None) if event.widget is dialog else None)
        picker.bind("<<ComboboxSelected>>", render)
        render()
        update_preview()
        ttk.Button(panel, text="打开预览", command=lambda: webbrowser.open(web.ORIGIN + "/preview")).pack(side="left")
        ttk.Button(panel, text="保存并应用", command=save).pack(anchor="e")

    def start(self, event=None):
        text = self.input.get("1.0", "end-1c")
        lines = list(segments(text))
        if not lines:
            return "break"
        reference, transcript = None, ""
        voice = self.voice.get()
        slot = self.selected_slot()
        if self.voice.get() == FIXED_VOICE or slot is not None:
            reference = self.sample_path(slot)
            try:
                transcript = reference.with_suffix(".transcript.txt").read_text(encoding="utf-8").strip()
                if not transcript or not reference.is_file():
                    raise OSError
            except (OSError, UnicodeError):
                self.status.set("请重新导入这个音色，并填写参考音频的原文")
                return "break"
        self.jobs.append((text, lines, voice, reference, transcript, speech.aishell_speaker() if voice == speech.AISHELL else None))
        self.input.delete("1.0", "end")
        self.input.edit_reset()
        self.input.focus_set()
        if self.busy:
            self.update_queue()
        else:
            self.start_next_job()
        return "break"

    def update_queue(self):
        self.queue_view.delete(0, "end")
        if self.submitted is not None:
            self.queue_view.insert("end", "正在处理  " + " ".join(self.submitted.split()))
        for index, (text, *_) in enumerate(self.jobs, 1):
            self.queue_view.insert("end", f"{index}.  " + " ".join(text.split()))
        count = self.queue_view.size()
        if count:
            self.queue_empty.pack_forget()
            self.queue_view.configure(height=min(count, 3))
            self.queue_view.pack(side="left", fill="x", expand=True)
        else:
            self.queue_view.pack_forget()
            self.queue_empty.pack(anchor="w", padx=2)
        if count > 3:
            self.queue_scroll.pack(side="right", fill="y", before=self.queue_view)
        else:
            self.queue_scroll.pack_forget()

    def start_next_job(self):
        if not self.jobs:
            self.busy = False
            if (self.voice.get() == speech.SYSTEM or voice_packs.is_local_voice(self.voice.get())):
                mambo.release()
            self.update_queue()
            return
        self.submitted, lines, self.run_voice, self.run_reference, self.run_transcript, self.run_speaker = self.jobs.popleft()
        self.busy = True
        self.pending = iter((line, None) for line in lines)
        self.update_queue()
        self.next_line()

    def slot_label(self, slot):
        name = self.slot_names[slot]
        return f"自定义 {slot} · {name}" if name else f"自定义 {slot}"

    def voice_options(self):
        options = (*(name for name in (voice_packs.HUAYAN,) if voice_packs.installed(name)),
                   speech.SYSTEM, *(name for name in voice_packs.MODELS if voice_packs.installed(name)), *voice_packs.custom_names(), mimo_cloud.NAME)
        if not mambo.locate():
            return options
        def available(slot):
            path = self.sample_path(slot)
            return path.is_file() and path.with_suffix(".transcript.txt").is_file()
        fixed = (FIXED_VOICE,) if available(None) else ()
        return (*options, *VOICES, *fixed, *(self.slot_label(slot) for slot in self.slot_names if available(slot)))

    def selected_slot(self):
        return next((slot for slot in self.slot_names if self.voice.get() == self.slot_label(slot)), None)

    def sample_path(self, slot):
        return FIXED_VOICE_FILE if slot is None else FIXED_VOICE_FILE.with_name(f"voice-{slot}.wav")

    def rename_slot(self):
        slot = self.selected_slot()
        if slot is None:
            return
        name = simpledialog.askstring("重命名音色", "输入新名称", initialvalue=self.slot_names[slot], parent=self.root)
        if name is None:
            return
        name = name.strip()
        if len(name) > 24:
            self.status.set("音色名称最多 24 个字")
            return
        try:
            VOICE_FILE.with_name(f"voice-{slot}.txt").write_text(name, encoding="utf-8")
        except OSError:
            self.status.set("无法保存音色名称")
            return
        self.slot_names[slot] = name
        self.picker.configure(values=self.voice_options())
        self.voice.set(self.slot_label(slot))
        self.save_voice()

    def choose_aishell_speaker(self):
        if self.busy:
            self.status.set("请先停止朗读，再试听")
            return
        dialog = self.new_dialog(self.settings_parent())
        dialog.title("AISHELL-3 音色")
        dialog.transient(self.settings_parent())
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=14)
        panel.pack(fill="both", expand=True)
        sid = tk.StringVar(dialog, str(speech.aishell_speaker()))
        last = speech.SPEAKER_COUNT - 1
        dialog.resizable(False, False)
        header = ttk.Frame(panel)
        header.pack(fill="x")
        ttk.Label(header, text=f"发音人编号（0–{last}）").pack(side="left", padx=(0, 16))
        stepper = ttk.Frame(header)
        stepper.pack(side="right")
        number = ttk.Entry(stepper, textvariable=sid, width=6, justify="center")
        slider = integer_slider(panel, sid, 0, last, length=300)
        slider.pack(fill="x", pady=(10, 6))

        def step(delta=0):
            try:
                value = int(sid.get())
            except ValueError:
                value = round(slider.get())
            slider.set(max(0, min(last, value + delta)))

        ttk.Button(stepper, text="−", width=3, command=lambda: step(-1)).pack(side="left")
        number.pack(side="left", padx=5)
        ttk.Button(stepper, text="＋", width=3, command=lambda: step(1)).pack(side="left")
        number.bind("<FocusOut>", lambda _: step())
        status = tk.StringVar(dialog)
        ttk.Label(panel, textvariable=status).pack(fill="x")
        footer = ttk.Frame(panel)
        footer.pack(fill="x", pady=(6, 0))
        result = queue.Queue()
        preview = self.wav.with_name("aishell-preview.wav")

        def selected():
            try:
                value = int(sid.get())
                if 0 <= value < speech.SPEAKER_COUNT:
                    return value
            except ValueError:
                pass
            status.set("请输入 0–173 的整数")
            return None

        def close():
            self.stop_audio()
            dialog.destroy()

        def save():
            value = selected()
            if value is not None:
                try:
                    speech.SPEAKER_FILE.write_text(str(value), encoding="utf-8")
                except OSError:
                    status.set("无法保存音色")
                    return
                self.status.set(f"AISHELL-3 · {value:03} 号")
                close()

        def listen():
            value = selected()
            if value is None:
                return
            self.stop_audio()
            audition.state(["disabled"])
            status.set(f"正在生成 {value:03} 号试听…")

            def run():
                try:
                    audio, _ = speech.synthesize("今天的风很轻，窗边的树叶在慢慢摇。", speech.AISHELL, speaker=value)
                except speech.SpeechError as exc:
                    result.put(str(exc))
                else:
                    result.put(audio)

            def poll():
                try:
                    audio = result.get_nowait()
                except queue.Empty:
                    dialog.after(50, poll)
                    return
                audition.state(["!disabled"])
                if isinstance(audio, str):
                    status.set(audio)
                    return
                try:
                    preview.write_bytes(audio)
                    winsound.PlaySound(str(preview), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                    status.set(f"试听：{value:03} 号")
                except (OSError, RuntimeError):
                    status.set("试听播放失败")

            threading.Thread(target=run, daemon=True).start()
            dialog.after(50, poll)

        ttk.Button(footer, text="使用此音色", style="Accent.TButton", command=save).pack(side="left")
        audition = ttk.Button(footer, text="试听", command=listen)
        audition.pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close)

    def show_description(self):
        if self.voice.get() == speech.AISHELL:
            self.speaker_button.pack(side="right", padx=(6, 0))
        else:
            self.speaker_button.pack_forget()
        if self.selected_slot() is None:
            self.rename_button.pack_forget()
        else:
            self.rename_button.pack(side="right", padx=(6, 0))

    def save_voice(self, event=None):
        self.show_description()
        try:
            VOICE_FILE.write_text(self.voice.get(), encoding="utf-8")
        except OSError:
            self.status.set("音色已切换，但无法保存选择")
        else:
            if event is not None and not self.busy:
                if (self.voice.get() == speech.SYSTEM or voice_packs.is_local_voice(self.voice.get())):
                    mambo.release()
                self.status.set(f"{self.voice.get()} · 回车朗读")

    def replay(self):
        if self.previous is not None and not self.busy:
            self.busy = True
            self.pending = iter(self.previous[1])
            self.next_line()

    def next_line(self):
        self.timer = None
        if self.prefetched is not None:
            line, result = self.prefetched
            self.prefetched = None
            self.play_line(line, result)
        elif self.prefetching or self.prefetch_line():
            self.status.set("正在生成语音…")
        else:
            if self.submitted is not None:
                self.previous = (self.submitted, self.recording)
                self.replay_button.state(["!disabled"])
                self.submitted = None
                self.recording = []
            self.status.set("朗读完成")
            self.start_next_job()

    def prefetch_line(self):
        item = next(self.pending, None)
        if item is None:
            return False
        self.prefetching = True
        line, cached = item
        generation = self.generation
        speed = round(self.speed.get(), 1)
        voice, reference, transcript, speaker = speech.SYSTEM, None, "", None
        if cached is None:
            voice, reference, transcript = self.run_voice, self.run_reference, self.run_transcript
            speaker = self.run_speaker

        def work():
            try:
                original = cached if cached is not None else speech.synthesize(line, voice, reference, transcript, speaker)
            except (mambo.EngineError, speech.SpeechError) as error:
                result = str(error)
            except OSError:
                result = "无法启动曼波引擎，请检查引擎位置"
            else:
                try:
                    playback = original if speed == 1.0 else change_speed(original[0], speed)
                    result = (original, playback)
                except (OSError, audioop.error, wave.Error, EOFError):
                    result = "语速调整失败，请切回 1.0×"
            self.results.put((generation, line, result))

        threading.Thread(target=work, daemon=True).start()
        return True

    def poll(self):
        self.poll_mic()
        while True:
            try:
                generation, line, result = self.results.get_nowait()
            except queue.Empty:
                break
            if generation != self.generation:
                continue
            self.prefetching = False
            self.prefetched = (line, result)
            if self.timer is None:
                self.next_line()
        self.root.after(40, self.poll)

    def play_line(self, line, result):
        if isinstance(result, str):
            self.stop()
            self.status.set(result)
            return
        original, (audio, duration) = result
        try:
            self.stop_audio()
            if self.vts.get():
                self.stream = cable_audio.play(audio)
                duration += self.stream.latency
            else:
                self.wav.write_bytes(audio)
                winsound.PlaySound(str(self.wav), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            hold = min(6.0, max(1.8, len(line) * 0.15))
            self.mic_owns_caption = False
            self.write_caption(line, duration + hold)
        except (RuntimeError, OSError, ImportError):
            self.stop()
            self.status.set("播放失败，请检查 CABLE Input 或关闭「送到 VTS」")
            return
        self.status.set("正在朗读…")
        if self.submitted is not None:
            self.recording.append((line, original))
        self.timer = self.root.after(round(duration * 1000), self.next_line)
        self.prefetch_line()

    def stop_audio(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        winsound.PlaySound(None, 0)

    def stop(self):
        self.generation += 1
        self.prefetching = False
        self.prefetched = None
        unsent = ([self.submitted] if self.submitted is not None else []) + [job[0] for job in self.jobs]
        self.jobs.clear()
        self.busy = False
        self.submitted = None
        self.recording = []
        if unsent:
            suffix = "\n" if self.input.get("1.0", "end-1c") else ""
            self.input.insert("1.0", "\n".join(unsent) + suffix)
        self.update_queue()
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.stop_audio()
        self.write_caption("")
        self.status.set("已停止")

    def edit_hotwords(self):
        dialog = self.new_dialog(self.settings_parent())
        dialog.title("识别热词")
        dialog.transient(self.settings_parent())
        panel = ttk.Frame(dialog, padding=14)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="每行一个词或短语。下次开麦时生效。").pack(anchor="w")
        editor = tk.Text(panel, width=48, height=13, undo=True, wrap="word")
        editor.pack(fill="both", expand=True, pady=8)
        editor.insert("1.0", mic_caption.hotword_text())
        actions = ttk.Frame(panel)
        actions.pack(fill="x")

        def restore():
            editor.delete("1.0", "end")
            editor.insert("1.0", mic_caption.DEFAULT_HOTWORDS)

        def save():
            try:
                mic_caption.save_hotwords(editor.get("1.0", "end-1c"))
            except OSError:
                messagebox.showerror("识别热词", "无法保存热词", parent=dialog)
                return
            dialog.destroy()

        ttk.Button(actions, text="恢复默认", command=restore).pack(side="left")
        ttk.Button(actions, text="保存", command=save).pack(side="right")
        editor.focus_set()

    def configure_mimo(self):
        parent = self.settings_parent()
        dialog = self.new_dialog(parent)
        dialog.title("MiMo 设置")
        dialog.transient(parent)
        dialog.resizable(False, False)
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=14)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="仅选择小米 MiMo 朗读时联网。").grid(row=0, column=0, columnspan=2, sticky="w")
        key = tk.StringVar(dialog)
        voice = tk.StringVar(dialog, mimo_cloud.preset())
        ttk.Label(panel, text="API Key").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(panel, textvariable=key, width=29, show="•").grid(row=1, column=1, sticky="ew", pady=7)
        if mimo_cloud.KEY_FILE.is_file():
            ttk.Label(panel, text="已保存 Key，留空可保留。").grid(row=2, column=1, sticky="w")
        ttk.Label(panel, text="预置音色").grid(row=3, column=0, sticky="w", pady=7)
        ttk.Combobox(panel, values=mimo_cloud.VOICES, textvariable=voice, state="readonly").grid(row=3, column=1, sticky="ew")

        def save(remove=False):
            try:
                value = key.get().strip()
                if remove or value:
                    mimo_cloud.save("" if remove else value, voice.get())
                else:
                    mimo_cloud.KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
                    mimo_cloud.VOICE_FILE.write_text(voice.get(), encoding="utf-8")
            except (OSError, ValueError):
                messagebox.showerror("MiMo 设置", "无法保存设置", parent=dialog)
                return
            dialog.destroy()

        if mimo_cloud.KEY_FILE.is_file():
            ttk.Button(panel, text="清除 Key", command=lambda: save(True)).grid(row=4, column=0, sticky="w")
        ttk.Button(panel, text="保存", style="Accent.TButton", command=save).grid(row=4, column=1, sticky="e")

    def manage_packs(self):
        if self.busy:
            self.status.set("请先停止朗读，再管理语音包")
            return
        dialog = self.new_dialog(self.settings_parent())
        dialog.title("语音包")
        dialog.transient(self.settings_parent())
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=14)
        panel.pack(fill="both", expand=True)
        progress = tk.StringVar(dialog)

        def refresh(selected=None):
            names = tuple(voice_packs.custom_packs())
            model_picker.configure(values=names)
            if selected in names:
                model_picker.set(selected)
            elif model_picker.get() not in names:
                model_picker.set(names[0] if names else "")
            custom_remove.state(["!disabled"] if names else ["disabled"])
            options = self.voice_options()
            self.picker.configure(values=options)
            if self.voice.get() not in options:
                self.voice.set(speech.default_voice())
                self.save_voice()
                self.status.set(f"已切回{self.voice.get()}")

        def custom_pack(remove=False, archive=None):
            try:
                if remove:
                    name = model_picker.get()
                    if not name:
                        return
                    voice_packs.remove_custom(name)
                else:
                    if archive is None:
                        folder = filedialog.askdirectory(parent=dialog, title="选择解压后的 sherpa-onnx VITS 语音包")
                        if not folder:
                            return
                        name = voice_packs.register_custom(folder)
                    else:
                        if not archive.lower().endswith(".tar.bz2"):
                            raise ValueError("请选择一个 .tar.bz2 语音包。")
                        progress.set("正在解压语音包…")
                        dialog.update_idletasks()
                        name = voice_packs.import_custom_archive(archive)
                    self.voice.set(name)
                    self.save_voice()
                refresh(None if remove else name)
                progress.set(f"已移除 {name}" if remove else f"已导入 {name}")
            except (OSError, ValueError, tarfile.TarError) as exc:
                progress.set("")
                messagebox.showerror("自定义语音包", str(exc), parent=dialog)

        def choose_archive():
            path = filedialog.askopenfilename(parent=dialog, filetypes=[("语音包", "*.tar.bz2")])
            if path:
                custom_pack(archive=path)

        def drop_archive(event):
            paths = dialog.tk.splitlist(event.data)
            if len(paths) == 1:
                custom_pack(archive=paths[0])
            else:
                messagebox.showerror("自定义语音包", "请一次拖入一个 .tar.bz2 语音包。", parent=dialog)

        dialog.drop_target_register(DND_FILES)
        dialog.dnd_bind("<<Drop>>", drop_archive)

        model_picker = ttk.Combobox(panel, state="readonly", width=30)
        model_picker.grid(row=0, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(panel, text="导入文件夹…", command=custom_pack).grid(row=1, column=2, padx=(6, 0), pady=3)
        custom_remove = ttk.Button(panel, text="移除", command=lambda: custom_pack(True))
        custom_remove.grid(row=0, column=2, pady=3)
        ttk.Button(panel, text="导入压缩包…", command=choose_archive).grid(row=1, column=1, pady=3)
        ttk.Label(panel, text="可将 .tar.bz2 拖到此窗口").grid(row=1, column=0, sticky="w")
        ttk.Label(panel, textvariable=progress).grid(row=2, column=0, columnspan=3, sticky="w")
        refresh()

    def close(self, restart=False):
        self.save_voice()
        if self.mic_stop is not None:
            self.mic_stop.set()
        self.stop()
        self.restart_requested = restart
        self.root.destroy()


if __name__ == "__main__":
    from web import Handler, ThreadingHTTPServer

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MiMoReader.Desktop")
    root = TkinterDnD.Tk()
    server = None
    restart = False
    try:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
        except OSError:
            root.withdraw()
            messagebox.showerror("咔咪字幕机", "字幕端口 8765 已被占用。请关闭旧版咔咪字幕机后重试。")
            root.destroy()
        else:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            with tempfile.TemporaryDirectory(prefix="kami-reader-") as folder:
                reader = Reader(root, folder)
                root.mainloop()
                restart = reader.restart_requested
    except OSError:
        messagebox.showerror("咔咪字幕机", "无法启动 OBS 字幕服务或创建临时文件。")
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        mambo.shutdown()
    if restart:
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.extend(("-B", str(Path(__file__).resolve())))
        subprocess.Popen(command, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
                         creationflags=subprocess.CREATE_NO_WINDOW)
