# 咔咪字幕机

**[下载最新版 · Windows x64](https://github.com/pinklarrrrk/kami-subtitle/releases/latest)** · [使用说明](#下载和使用) · [语音包](#朗读音色)

免费的 Windows 朗读与字幕工具。可以打字朗读，也可以把麦克风里的中英混合语音实时转成 OBS 字幕。

## 下载和使用

1. 在 [GitHub Releases](https://github.com/pinklarrrrk/kami-subtitle/releases/latest) 下载 Windows x64 ZIP。
2. 解压整个 ZIP，双击「咔咪字幕机.exe」。
3. 输入文字后按回车朗读，按 Shift+回车换行，按 Esc 停止。想用麦克风时，点「开麦字幕」。支持中英混说，字幕会在停顿时分句。

在「设置 → 识别热词」可以编辑主播名、游戏名和常用短语，每行一条。保存后，下次开启麦克风字幕时生效。

## 日语双语字幕 DLC

[单独下载日语字幕 DLC](https://github.com/pinklarrrrk/kami-subtitle/releases/tag/dlc-japanese-v1.0.0)（需要咔咪 v1.0.11 或更新版本）。解压后双击 `Install.cmd`，首次安装会从上游下载约 1.4 GB 组件。装好后识别和翻译均在本机运行，无需 API Key。

在「设置 → 麦克风字幕」勾选「日语 → 日中双语」，再点「开麦字幕」。停顿后先显示日文，译文完成后补到下一行。自动翻译可能出错。

## 朗读音色

- **Windows 系统朗读**：默认使用，离线可用。
- **小米 MiMo**：在「设置 → MiMo 设置」保存自己的 API Key，再从音色列表选择「小米 MiMo」。使用时需要联网。
- **自定义离线语音**：支持兼容 sherpa-onnx 的 VITS 语音包和 Matcha 中英双语包。语音模型单独下载。

### 导入自定义离线语音包

一句话里经常夹英文？**优先选 Matcha 中英双语**。下载模型和声码器后，按表格下方的步骤导入。

| 下载 | 语言 | 解压后选择的文件夹 |
| --- | --- | --- |
| [★ Matcha 中英双语（首选）](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/matcha-icefall-zh-en.tar.bz2) | 支持一句里中英混读 | `matcha-icefall-zh-en`（需另下 [Vocos 16 kHz 声码器](https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/vocos-16khz-univ.onnx)，见下方导入步骤） |
| [Piper 华燕](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-zh_CN-huayan-medium.tar.bz2) | 普通话 | `vits-piper-zh_CN-huayan-medium` |
| [AISHELL-3](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-icefall-zh-aishell3.tar.bz2) | 普通话 | `vits-icefall-zh-aishell3` |
| [凡尘 WNJ](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-hf-fanchen-wnj.tar.bz2) | 普通话男声 | `vits-zh-hf-fanchen-wnj` |
| [MeloTTS 中英双语](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2) | 支持一句里中英混读 | v1.0.8 起可直接导入官方压缩包 |
| [Piper Amy](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-amy-low.tar.bz2) | 美式英语 | `vits-piper-en_US-amy-low` |
| [Piper Lessac](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-lessac-medium.tar.bz2) | 美式英语 | `vits-piper-en_US-lessac-medium` |

下载后，打开「设置 → 语音包」，把 `.tar.bz2` 拖进窗口，或点击「导入压缩包…」。如果已解压，点击「导入文件夹…」，选中直接包含以下文件的那一层：

- 一个 VITS `.onnx` 模型；如果同时附带同名的 `.int8.onnx`，咔咪会自动选择标准版
- `tokens.txt`
- `lexicon.txt` 或完整的 `espeak-ng-data/` 文件夹

AISHELL-3 使用默认发音人。只有 `.onnx` 和 `.onnx.json` 的 Piper 包不能直接导入。导入后会自动选中新音色；可以保留多个音色，点「移除」不会删除原文件。

华燕、AISHELL-3、凡尘 WNJ 和 Matcha Baker 会用中文近似发音逐字母朗读英文，例如把 `OBS` 读成「欧比艾斯」。字幕保留原文。需要按英文单词发音时，推荐使用 Matcha 中英双语。

### 导入 Matcha 中英双语

1. 下载并解压 [Matcha 中英双语模型](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/matcha-icefall-zh-en.tar.bz2)。
2. 下载 [Vocos 16 kHz 声码器](https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/vocos-16khz-univ.onnx)，放到和 `model-steps-3.onnx` 同一层。保留词典、`espeak-ng-data` 和 `.fst` 文件。
3. 在「设置 → 语音包 → 导入文件夹」选择该目录。导入后会自动切换到「Matcha 中英双语」。

此入口支持 `matcha-icefall-zh-en`，中文单语的 Matcha Baker 使用不同的声码器。

## 接入 OBS 和 VTube Studio

1. 在咔咪字幕机里点「OBS 字幕地址」复制链接。
2. 在 OBS 添加「浏览器」来源，关闭「本地文件」，粘贴链接。宽高设为画布尺寸，例如 1920 × 1080。

在「设置 → 字幕样式」可切换字幕和气泡，预览并调整字体、颜色、底色透明度和换行字数。麦克风识别只输出字幕；要录入朗读声音，请在 OBS 添加相应的音频来源。

要用朗读声音驱动口型，在「设置 → 字幕与输出」点「一键安装虚拟麦克风」，按提示安装 VB-CABLE 并重启电脑。然后勾选「送到 VTS」，在 VTube Studio 选择「CABLE Output」作为麦克风。

## 从源码构建

在 Windows x64 安装 Python 3.14。下载并解压 [Zipformer 中英识别模型](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20-mobile.tar.bz2)，将环境变量 `KAMI_ASR_MODEL` 指向解压后的模型目录，然后运行：

```powershell
py -3.14 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3 pywin32==311 sherpa-onnx==1.12.40 tkinterdnd2==0.7.0 sounddevice==0.5.6 audioop-lts==0.2.2
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm Kami.spec
```

构建结果位于 `dist/Kami-Windows-x64`。

## 许可、致谢与反馈

本软件采用 Vibe Coding 方式开发，由用户提出需求和迭代，AI 协助编写代码。

原创代码使用 [MIT](LICENSE)，原创说明文字和标志使用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。第三方组件的致谢和许可见 [THIRD-PARTY.md](THIRD-PARTY.md)。

问题反馈：在「设置 → 关于 · 问题反馈」复制模板，填写后发到 **pinklark@qq.com**。
