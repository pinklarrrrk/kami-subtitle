# 咔咪字幕机

免费的 Windows 朗读与字幕工具。可以打字朗读，也可以把麦克风里的普通话实时转成 OBS 字幕。

## 下载和使用

1. 在 [GitHub Releases](https://github.com/pinklarrrrk/kami-subtitle/releases/latest) 下载 Windows x64 ZIP。
2. 解压整个 ZIP，双击「咔咪字幕机.exe」。保留旁边的 `_internal` 文件夹，无需安装 Python。
3. 输入文字后按回车朗读，按 Shift+回车换行，按 Esc 停止。想用麦克风时，点「开麦字幕」。

## 朗读音色

- **Windows 系统朗读**：默认使用，离线可用。
- **小米 MiMo**：在「设置 → MiMo 设置」保存自己的 API Key，再从音色列表选择「小米 MiMo」。使用时需要联网。
- **自定义离线语音**：可以导入兼容 sherpa-onnx 的 VITS 语音包。下载包不附带第三方朗读模型。

### 导入自定义离线语音包

下面是 sherpa-onnx 提供的离线语音包，按需要选一个下载：

| 下载 | 语言 | 解压后选择的文件夹 |
| --- | --- | --- |
| [Piper 华燕](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-zh_CN-huayan-medium.tar.bz2) | 普通话 | `vits-piper-zh_CN-huayan-medium` |
| [AISHELL-3](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-icefall-zh-aishell3.tar.bz2) | 普通话 | `vits-icefall-zh-aishell3` |
| [凡尘 WNJ](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-hf-fanchen-wnj.tar.bz2) | 普通话男声 | `vits-zh-hf-fanchen-wnj` |
| [MeloTTS 中英双语](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2) | 普通话、英语 | `vits-melo-tts-zh_en` |
| [Piper Amy](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-amy-low.tar.bz2) | 美式英语 | `vits-piper-en_US-amy-low` |
| [Piper Lessac](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-lessac-medium.tar.bz2) | 美式英语 | `vits-piper-en_US-lessac-medium` |

下载并解压后，在「设置 → 语音包 → 自定义离线语音」点「导入文件夹…」。选中直接包含以下文件的那一层：

- 一个 VITS `.onnx` 模型
- `tokens.txt`
- `lexicon.txt` 或完整的 `espeak-ng-data/` 文件夹

AISHELL-3 通过这个入口使用默认发音人。只有 `.onnx` 和 `.onnx.json` 的 Piper 包，以及使用不同模型结构的 Matcha Baker，不能从这个入口导入。导入后软件会自动选中这个音色。重新导入可替换，点「移除」不会删除模型文件。

## 接入 OBS 和 VTube Studio

1. 在咔咪字幕机里点「OBS 字幕地址」复制链接。
2. 在 OBS 添加「浏览器」来源，关闭「本地文件」，粘贴链接。宽高设为画布尺寸，例如 1920 × 1080。

在「设置 → 字幕样式」可切换字幕和气泡，预览并调整字体、颜色、底色透明度和换行字数。麦克风识别只输出字幕；要录入朗读声音，请在 OBS 添加相应的音频来源。已配置 VB-CABLE 的用户可勾选「送到 VTS」，用朗读声音驱动口型。

## 从源码构建

在 Windows x64 安装 Python 3.12。从 [Vosk 模型页](https://alphacephei.com/vosk/models) 下载并解压 `vosk-model-small-cn-0.22`，将环境变量 `KAMI_VOSK_MODEL` 指向解压后的模型目录，然后运行：

```powershell
py -3.12 -m pip install pyinstaller==6.22.3 pywin32==311 sherpa-onnx==1.12.40
py -3.12 -m pip install --target src/mic_vendor vosk==0.3.45 sounddevice==0.5.6
py -3.12 -m PyInstaller --noconfirm Kami.spec
```

构建结果位于 `dist/Kami-Windows-x64`。

## 许可、致谢与反馈

本软件采用 Vibe Coding 方式开发，由用户提出需求和迭代，AI 协助编写代码。

原创代码使用 [MIT](LICENSE)，原创说明文字和标志使用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。第三方组件的致谢和许可见 [THIRD-PARTY.md](THIRD-PARTY.md)。

问题反馈：在「设置 → 关于 · 问题反馈」复制模板，填写后发到 **pinklark@qq.com**。
