# 咔咪字幕机

当前源码版本：v1.0.0。此仓库发布源码；不附带华燕、Matcha Baker、AISHELL-3 或曼波语音包。缺少华燕资源时，源码构建版默认使用 Windows 系统语音。

Windows x64 用户解压整个便携包，双击「咔咪字幕机.exe」，无需安装 Python、FFmpeg 或另行下载普通话识别模型。请保留 EXE 旁边的 `_internal` 文件夹。取消勾选「置顶」可恢复普通窗口。小窗会自动提供 OBS 字幕页；也可在浏览器打开 `http://127.0.0.1:8765/` 使用网页输入。若需要把朗读输出给 VTube Studio 当麦克风使用，该用途仍需要系统里已配置的 VB-CABLE。

输入文字后点击朗读或按回车（网页版用 Ctrl+Enter），Esc 停止。桌面端用 Shift+Enter 手动换行，字幕保留输入中的换行。本机版默认使用 Piper 华燕离线朗读，无需 API Key 或显卡。也可手动选择 Windows 系统朗读。

在「设置 → 语音包」点击「安装」即可。随附资源的本机版会自动使用便携包内的 AISHELL-3 和 Matcha Baker；如需自选保存位置，先点「浏览」，留空则使用默认位置。曼波的可选独立包为 `Kami-Mambo-Standalone` 文件夹，放到 EXE 旁或应用文件夹同级后即可一键安装。主程序不含曼波组件，不搜索或复用旧版安装；安装盘需至少有 16 GB 可用空间。安装后从音色下拉框切换。选中 AISHELL-3 后可点击「切换音色」试听并保存发音人，无需额外下载；卸载当前使用的包会切回默认音色。

在「设置 → MiMo 设置」可保存 API Key、选择预置音色，然后从音色列表选「小米 MiMo」。Key 使用 Windows 用户加密保存；只有选择 MiMo 朗读时才会调用联网服务。

OBS 添加「浏览器」来源，关闭「本地文件」，粘贴页面中「复制 OBS 字幕地址」给出的地址。按画布尺寸设置宽高，例如 1920×1080。字幕背景透明，默认在画布底部居中；播完后按字数额外保留 1.8–6 秒，手动停止立即清空。需要录入朗读声音时另加桌面音频或应用程序音频捕获。

src/web.py 是本机服务，src/reader.html 是输入页，src/obs.html 是字幕页。src/app.py 是独立置顶输入窗。

默认从扬声器播放；需要通过 VB-CABLE 驱动 VTube Studio 口型时，在设置勾选「送到 VTS」。





桌面小窗的「开麦字幕」使用 Windows 默认录音设备和本机普通话识别，只更新 OBS 字幕，不播放声音。点「关麦 · 打字」后回到回车排队朗读。打字朗读期间优先显示 TTS 字幕。字幕源地址不变。

打开「设置 → 字幕样式」，可导入 TTF、OTF、WOFF 或 WOFF2 字体，调整字号、文字颜色、底色透明度和每行最多字数（0 为自动）。字幕模式支持外描边及描边颜色，气泡按最长一行自动加宽，最多占画布的 96%。点「打开预览」查看实时效果，保存后应用到 OBS。

本软件采用 Vibe Coding 方式开发，由用户提出需求并迭代，AI 协助编写代码。感谢 MamboTTS、GPT-SoVITS、Vosk、python-sounddevice、思源黑体、Python 和 Tcl/Tk。

本项目原创说明文字与咔咪标志使用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。转载或改编时请注明「咔咪字幕机」、附协议链接并说明是否修改。该协议不覆盖程序代码、第三方依赖、字体及语音服务；第三方内容以各自条款为准。

原创程序代码使用 [MIT](LICENSE)；第三方授权与署名见 [THIRD-PARTY.md](THIRD-PARTY.md)。

问题反馈：打开「设置 → 关于 · 问题反馈」，复制模板、填写后发送至 pinklark@qq.com。

从源码构建：在 Windows x64 上安装 Python 3.12，从 [Vosk 模型页](https://alphacephei.com/vosk/models) 下载并解压 `vosk-model-small-cn-0.22`，将环境变量 `KAMI_VOSK_MODEL` 指向解压后的模型目录。然后运行：

```powershell
py -3.12 -m pip install pyinstaller==6.22.3 pywin32==311 sherpa-onnx==1.12.40
py -3.12 -m pip install --target src/mic_vendor vosk==0.3.45 sounddevice==0.5.6
py -3.12 -m PyInstaller --noconfirm Kami.spec
```

产物在 `dist/Kami-Windows-x64`。发布时保留整个目录，并附上项目授权、第三方声明及模型许可。
