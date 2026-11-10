param([string]$Cache)

$ErrorActionPreference = 'Stop'
$homePath = Join-Path $env:LOCALAPPDATA 'MiMoReader'
$target = Join-Path $homePath 'japanese-captions'
if (Test-Path -LiteralPath $target) {
    throw "DLC folder already exists: $target. Move it aside before reinstalling."
}
New-Item -ItemType Directory -Path $homePath -Force | Out-Null
$work = Join-Path (Resolve-Path -LiteralPath $homePath).Path ('japanese-setup-' + [guid]::NewGuid().ToString('N'))
$pack = Join-Path $work 'japanese-captions'
New-Item -ItemType Directory -Path $pack -Force | Out-Null

function Get-Asset($url, $name, $hash) {
    $file = Join-Path $work $name
    if ($Cache) {
        Copy-Item -LiteralPath (Join-Path $Cache $name) -Destination $file
    } else {
        Write-Host "Downloading $name"
        curl.exe --fail --location --retry 2 --output $file $url
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $name" }
    }
    if ((Get-FileHash -LiteralPath $file).Hash -ne $hash) { throw "SHA-256 mismatch: $name" }
    $file
}

try {
    $asr = 'sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17'
    $asrBase = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models'
    $archive = Get-Asset "$asrBase/$asr.tar.bz2" "$asr.tar.bz2" '7D1EFA2138A65B0B488DF37F8B89E3D91A60676E416F515B952358D83DFD347E'
    tar.exe -xf $archive -C $work "$asr/model.int8.onnx" "$asr/tokens.txt" "$asr/LICENSE"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot extract SenseVoice' }
    Get-ChildItem -LiteralPath (Join-Path $work $asr) -File | Move-Item -Destination $pack
    $vad = Get-Asset "$asrBase/silero_vad.onnx" 'silero_vad.onnx' '9E2449E1087496D8D4CABA907F23E0BD3F78D91FA552479BB9C23AC09CBB1FD6'
    Move-Item -LiteralPath $vad -Destination $pack
    $runtime = 'llama-b12244-bin-win-cpu-x64.zip'
    $archive = Get-Asset "https://github.com/ggml-org/llama.cpp/releases/download/b12244/$runtime" $runtime '318F11FADCBC3A86541EC55D9930CC76646C6B8D2FF18798C8477E9FF0DC452A'
    Expand-Archive -LiteralPath $archive -DestinationPath $pack
    $mt = 'HY-MT1.5-1.8B-Q4_K_M.gguf'
    $weights = Get-Asset "https://huggingface.co/tencent/HY-MT1.5-1.8B-GGUF/resolve/main/$mt" $mt '4383AC0C3C8E476DE98FF979C2A3F069F8C4FB385E7860CF2D28DA896CC477C7'
    Move-Item -LiteralPath $weights -Destination $pack
    if (!(Test-Path -LiteralPath (Join-Path $pack 'llama-server.exe') -PathType Leaf)) { throw 'Missing translation runtime' }
    Move-Item -LiteralPath $pack -Destination $target
    Write-Host "Installed: $target"
} finally {
    $resolved = (Resolve-Path -LiteralPath $work).Path
    if ((Split-Path -Parent $resolved) -eq (Resolve-Path -LiteralPath $homePath).Path -and
        (Split-Path -Leaf $resolved) -match '^japanese-setup-[0-9a-f]{32}$') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
