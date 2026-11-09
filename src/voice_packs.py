from array import array
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import wave
import zipfile

import mambo


HUAYAN = "Piper 华燕"
MATCHA = "Matcha Baker"
CUSTOM = "自定义离线语音"
MODELS = {"AISHELL-3": "aishell3", MATCHA: "matcha-baker"}
ARCHIVES = {"AISHELL-3": "Kami-AISHELL-3.zip", MATCHA: "Kami-Matcha-Baker.zip"}
HOME = mambo.DATA / "voice-packs"
CUSTOM_PATH = HOME / "custom-vits.txt"
FILES = {
    "AISHELL-3": ("model.onnx", "tokens.txt", "lexicon.txt"),
    MATCHA: ("model-steps-3.onnx", "vocos-22khz-univ.onnx", "tokens.txt", "lexicon.txt"),
    HUAYAN: ("zh_CN-huayan-medium.onnx", "tokens.txt", "espeak-ng-data/phondata"),
}
lock = threading.Lock()
engines = {}


def root_for(name):
    if name == CUSTOM:
        return Path(CUSTOM_PATH.read_text(encoding="utf-8"))
    if name == HUAYAN:
        return bundled_root() / "voice-packs" / "huayan"
    try:
        return Path((HOME / (MODELS[name] + ".txt")).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HOME / MODELS[name]


def is_local_voice(name):
    return name in (HUAYAN, CUSTOM) or name in MODELS


def installed(name):
    try:
        return complete(name, root_for(name))
    except (OSError, UnicodeError):
        return False


def complete(name, root):
    if name == CUSTOM:
        return (root.is_dir() and len(list(root.glob("*.onnx"))) == 1
                and (root / "tokens.txt").is_file()
                and ((root / "lexicon.txt").is_file() or (root / "espeak-ng-data" / "phondata").is_file()))
    return all((root / filename).is_file() for filename in FILES[name])


def register_custom(folder):
    root = Path(folder).resolve()
    if not complete(CUSTOM, root):
        raise ValueError("请选择包含一个 VITS ONNX、tokens.txt，以及 lexicon.txt 或 espeak-ng-data 的文件夹。")
    if not str(root).isascii() and str(HOME).isascii():
        HOME.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HOME, prefix="vits-staging-") as staging:
            copied = Path(staging) / "model"
            shutil.copytree(root, copied)
            target = HOME / Path(staging).name.replace("vits-staging-", "vits-import-")
            copied.rename(target)
            root = target
    with lock:
        CUSTOM_PATH.parent.mkdir(parents=True, exist_ok=True)
        CUSTOM_PATH.write_text(str(root), encoding="utf-8")
        engines.pop(CUSTOM, None)


def import_custom_archive(path):
    HOME.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=HOME, prefix="vits-staging-") as staging:
        root = Path(staging)
        with tarfile.open(path, "r:bz2") as archive:
            def safe_file(member, destination):
                if not (member.isdir() or member.isfile()):
                    raise ValueError("语音包只能包含普通文件和文件夹。")
                return tarfile.data_filter(member, destination)

            archive.extractall(root, filter=safe_file)
        candidates = {model.parent for model in root.rglob("*.onnx") if complete(CUSTOM, model.parent)}
        if len(candidates) != 1:
            raise ValueError("压缩包里需要有且只有一个兼容的 VITS 模型文件夹。")
        target = HOME / root.name.replace("vits-staging-", "vits-import-")
        selected = candidates.pop()
        if selected == root:
            target.mkdir()
            for entry in root.iterdir():
                entry.rename(target / entry.name)
        else:
            selected.rename(target)
        register_custom(target)


def remove_custom():
    with lock:
        CUSTOM_PATH.unlink(missing_ok=True)
        engines.pop(CUSTOM, None)


def install(name, archive, folder=HOME):
    HOME.mkdir(parents=True, exist_ok=True)
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as folder, zipfile.ZipFile(archive) as package:
        root = Path(folder)
        if sum(item.file_size for item in package.infolist()) > 2_000_000_000:
            raise ValueError("语音包太大")
        for item in package.infolist():
            parts = PurePosixPath(item.filename).parts
            if not parts and item.is_dir():
                continue
            if not parts or any(part == "/" or part.endswith((".", " ")) or ":" in part or "\\" in part
                                or Path(part).is_reserved() for part in parts):
                raise ValueError("语音包路径无效")
            target = root.joinpath(*parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        if not complete(name, root):
            raise ValueError(f"{name} 语音包不完整")
        with lock:
            target = root.parent / MODELS[name]
            if target.exists():
                raise ValueError("请先卸载旧语音包")
            os.replace(root, target)
            try:
                (HOME / (MODELS[name] + ".txt")).write_text(str(target), encoding="utf-8")
            except OSError:
                shutil.rmtree(target)
                raise


def uninstall(name):
    with lock:
        engines.pop(name, None)
        root = root_for(name)
        if root.exists():
            if root.name != MODELS[name] or root.is_symlink() or root.is_junction():
                raise ValueError("语音包不在管理目录内")
            shutil.rmtree(root)
        (HOME / (MODELS[name] + ".txt")).unlink(missing_ok=True)


def bundled_root():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1] / "dist"


MAMBO_FILES = ("7zr.exe", "engine.7z", "models.zip")
MAMBO_MARKER = ".kami-mambo-package"


def mambo_package():
    base = bundled_root()
    for package in (base / "Kami-Mambo-Standalone", base.parent / "Kami-Mambo-Standalone"):
        if all((package / name).is_file() for name in MAMBO_FILES):
            return package
    return None


def install_available(name, folder=None):
    base = bundled_root()
    if name != "曼波":
        install(name, base / "voice-packs" / ARCHIVES[name], folder or HOME)
        return
    package = mambo_package()
    if package is None:
        raise ValueError("未找到曼波独立语音包")
    parent = Path(folder or HOME).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / "MamboEngine"
    if target.exists():
        raise ValueError("保存位置已有 MamboEngine，请先卸载或换个文件夹")
    if shutil.disk_usage(parent).free < 16_000_000_000:
        raise ValueError("安装曼波至少需要 16 GB 可用空间")
    mambo.DATA.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        staged = Path(temp) / target.name
        staged.mkdir()
        result = subprocess.run(
            [str(package / "7zr.exe"), "x", str(package / "engine.7z"), f"-o{staged}", "-y"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            raise ValueError("曼波引擎解压失败，请检查独立包是否完整")
        models = staged / "models"
        models.mkdir()
        with zipfile.ZipFile(package / "models.zip") as archive:
            for name in ("manbo_e8_s168.pth", "manbo-e10.ckpt", "refer.wav"):
                with archive.open(name) as source, (models / name).open("wb") as output:
                    shutil.copyfileobj(source, output)
        if not mambo.engine_files(staged):
            raise ValueError("曼波独立包缺少运行文件")
        (staged / MAMBO_MARKER).touch()
        os.replace(staged, target)
        try:
            mambo.LOCATION.write_text(str(target), encoding="utf-8")
        except OSError:
            shutil.rmtree(target)
            raise


def uninstall_mambo():
    root = mambo.locate()
    mambo.release()
    if root and root.name == "MamboEngine" and not (root.is_symlink() or root.is_junction()):
        if (root / MAMBO_MARKER).is_file():
            shutil.rmtree(root)
    mambo.LOCATION.unlink(missing_ok=True)


def synthesize(name, text, speaker=0):
    import sherpa_onnx as sherpa

    with lock:
        if not installed(name):
            raise ValueError("语音包尚未安装")
        if name not in engines:
            root = root_for(name)
            def file(filename):
                return str(root / filename)
            if name == MATCHA:
                config = sherpa.OfflineTtsMatchaModelConfig(
                    acoustic_model=file("model-steps-3.onnx"), vocoder=file("vocos-22khz-univ.onnx"),
                    tokens=file("tokens.txt"), lexicon=file("lexicon.txt"),
                )
                model = sherpa.OfflineTtsModelConfig(matcha=config, num_threads=2, provider="cpu")
            elif name == CUSTOM:
                config = sherpa.OfflineTtsVitsModelConfig(
                    model=str(next(root.glob("*.onnx"))), tokens=file("tokens.txt"),
                    lexicon=file("lexicon.txt") if (root / "lexicon.txt").is_file() else "",
                    data_dir=file("espeak-ng-data") if (root / "espeak-ng-data" / "phondata").is_file() else "",
                )
                model = sherpa.OfflineTtsModelConfig(vits=config, num_threads=2, provider="cpu")
            else:
                config = sherpa.OfflineTtsVitsModelConfig(
                    model=file("zh_CN-huayan-medium.onnx" if name == HUAYAN else "model.onnx"),
                    tokens=file("tokens.txt"), lexicon="" if name == HUAYAN else file("lexicon.txt"),
                    data_dir=file("espeak-ng-data") if name == HUAYAN else "",
                )
                model = sherpa.OfflineTtsModelConfig(vits=config, num_threads=2, provider="cpu")
            rules = ",".join(str(path) for path in sorted(root.glob("*.fst")))
            engines[name] = sherpa.OfflineTts(sherpa.OfflineTtsConfig(model=model, rule_fsts=rules))
        audio = engines[name].generate(text, sid=speaker)
    pcm = array("h", (round(max(-1, min(1, sample)) * 32767) for sample in audio.samples))
    if not pcm:
        raise ValueError("语音包没有生成声音")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, audio.sample_rate, 0, "NONE", "not compressed"))
        wav.writeframes(pcm.tobytes())
    return output.getvalue(), len(pcm) / audio.sample_rate
