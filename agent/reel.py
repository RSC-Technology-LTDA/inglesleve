"""Monta o Reel do dia: cenas em PNG (Playwright) + narração (edge-tts) → reel.mp4 com ffmpeg.

Cada cena fica na tela o tempo da sua narração (PT do narrador, pausa, inglês da voz nativa),
com um zoom lento para dar movimento.
"""

import asyncio
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import edge_tts
from playwright.sync_api import sync_playwright

from .render import _AUTOFIT_JS, STORY_SIZE, _css, _env, pick_theme
from .schemas import ContentPack, ReelScene

FPS = 30
GAP = 0.25        # pausa entre a fala em PT e o inglês
TAIL = 0.5        # respiro no fim de cada cena
MIN_SCENE = 1.8   # cenas sem narração (ou muito curtas) ficam pelo menos isso
ZOOM = 0.05       # quanto cada cena aproxima do início ao fim
VOICES = {"pt": "pt-BR-AntonioNeural", "en": "en-US-AvaMultilingualNeural"}


def _title_size(scene: ReelScene) -> int:
    n = len(scene.title.replace("*", ""))
    if scene.kind in ("hook", "cta"):
        return 210 if n < 14 else (175 if n < 24 else 140)
    return 170 if n < 12 else (140 if n < 22 else (112 if n < 36 else 94))


def render_scenes(pack: ContentPack, brand: dict, work: Path, seed: Optional[int]) -> list:
    css = _css(brand, pick_theme(brand, pack, seed), *STORY_SIZE)
    tpl = _env.get_template("reel.html.j2")
    files = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": STORY_SIZE[0], "height": STORY_SIZE[1]})
        for i, scene in enumerate(pack.reel.scenes, 1):
            page.set_content(tpl.render(scene=scene, brand=brand, base_css=css, size=_title_size(scene)), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.evaluate(_AUTOFIT_JS)
            path = work / f"scene_{i:02d}.png"
            page.screenshot(path=str(path))
            files.append(path)
        browser.close()
    return files


def _speak(text: str, voice: str, path: Path, attempts: int = 4) -> None:
    # O serviço de voz às vezes não devolve áudio; tenta de novo antes de desistir.
    for n in range(attempts):
        try:
            asyncio.run(edge_tts.Communicate(text, voice).save(str(path)))
            return
        except edge_tts.exceptions.EdgeTTSException:
            if n == attempts - 1:
                raise
            time.sleep(2 * (n + 1))


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def scene_audio(scene: ReelScene, voices: dict, work: Path, i: int) -> Path:
    """Narração da cena em WAV, já com a pausa e o respiro final."""
    parts = []
    for lang, text in (("pt", scene.say_pt), ("en", scene.say_en)):
        if text.strip():
            mp3 = work / f"say_{i:02d}_{lang}.mp3"
            _speak(text.strip(), voices[lang], mp3)
            parts.append(mp3)
    total = sum(_duration(p) for p in parts) + GAP * max(len(parts) - 1, 0)
    dur = max(total + TAIL, MIN_SCENE)
    wav = work / f"scene_{i:02d}.wav"
    if not parts:
        _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{dur:.3f}", str(wav))
        return wav
    inputs, chain = [], []
    for n, p in enumerate(parts):
        if n:
            inputs += ["-f", "lavfi", "-t", str(GAP), "-i", "anullsrc=r=48000:cl=mono"]
        inputs += ["-i", str(p)]
    streams = len(parts) * 2 - 1
    for n in range(streams):
        chain.append(f"[{n}]aresample=48000,aformat=channel_layouts=mono[a{n}]")
    joined = "".join(f"[a{n}]" for n in range(streams))
    chain.append(f"{joined}concat=n={streams}:v=0:a=1,apad=whole_dur={dur:.3f}[out]")
    _ffmpeg(*inputs, "-filter_complex", ";".join(chain), "-map", "[out]", "-t", f"{dur:.3f}", str(wav))
    return wav


def scene_clip(png: Path, wav: Path, work: Path, i: int) -> Path:
    frames = max(int(_duration(wav) * FPS), 1)
    w, h = STORY_SIZE
    # Amplia antes do zoompan para o movimento não "tremer" por arredondamento de pixel.
    video = (
        f"[0]scale={w * 2}:{h * 2},"
        f"zoompan=z='1+{ZOOM}*on/{frames}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={w}x{h}:fps={FPS},"
        "format=yuv420p[v]"
    )
    clip = work / f"clip_{i:02d}.mp4"
    _ffmpeg(
        "-loop", "1", "-framerate", str(FPS), "-i", str(png), "-i", str(wav),
        "-filter_complex", video, "-map", "[v]", "-map", "1:a", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(clip),
    )
    return clip


def render_reel(pack: ContentPack, brand: dict, out_dir: Path, seed: Optional[int] = None) -> Optional[Path]:
    """Gera out_dir/reel.mp4 e a capa out_dir/reel_cover.png. Sem roteiro no pacote, não faz nada."""
    if not pack.reel or not pack.reel.scenes:
        return None
    voices = {**VOICES, **brand.get("voices", {})}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        pngs = render_scenes(pack, brand, work, seed)
        clips = []
        for i, (scene, png) in enumerate(zip(pack.reel.scenes, pngs), 1):
            clips.append(scene_clip(png, scene_audio(scene, voices, work, i), work, i))
        listing = work / "clips.txt"
        listing.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
        reel = out_dir / "reel.mp4"
        _ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(reel))
        shutil.copy(pngs[0], out_dir / "reel_cover.png")
    print(f"Reel de {_duration(reel):.1f}s em {reel}")
    return reel
