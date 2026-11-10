# 第三方组件

- 麦克风字幕使用 [sherpa-onnx Zipformer 中英模型](https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20)，模型卡标注 Apache License 2.0。
- [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) 使用 MIT License，底层音频库 [PortAudio](https://www.portaudio.com/license.html) 使用其 MIT 风格许可。
- [思源黑体](https://github.com/adobe-fonts/source-han-sans) 由 Adobe 和 Google 等贡献，使用 SIL Open Font License 1.1，许可全文随字体分发。
- [CPython](https://docs.python.org/3.14/license.html) 使用 Python Software Foundation License；[Tcl/Tk](https://www.tcl-lang.org/software/tcltk/license.html) 使用各自附带的许可。
- [PyInstaller](https://pyinstaller.org/) 用于生成便携包，生成的程序适用其引导程序分发例外。
- [pywin32](https://github.com/mhammond/pywin32) 用于调用 Windows SAPI 和启动安装程序。
- [audioop-lts](https://pypi.org/project/audioop-lts/) 为 Python 3.14 提供音频处理兼容支持。
- [VB-CABLE](https://vb-audio.com/Cable/index.htm) 由 VB-Audio 提供，安装时从其官方下载站获取，咔咪发行包不包含驱动。
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 用于运行可选语音模型，使用 Apache License 2.0；模型来源为其 [TTS 模型发布页](https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models)，AISHELL-3 模型作为独立资源随便携包提供。
- 本机版的 Piper 华燕和 Matcha Baker / Vocos 来自 sherpa-onnx 的模型发布资源。华燕随附模型卡注明训练数据许可未知；这些本机试听与使用资源未发布为公开发行版。
- 打字朗读对接 [MamboTTS](https://github.com/Tsukimisaka/MamboTTS)（Tsukimisaka）与 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 的本机 API。公开包不分发 GPT-SoVITS 整合包、曼波权重或参考音频；另行取得的组件遵循各自许可。

- TkinterDnD2 和 tkDnD 提供 Windows 文件拖放，许可见随包附带的第三方许可。

打包目录的 `_internal/licenses` 保留所收集的第三方许可证；字体许可在 `_internal/fonts`。
