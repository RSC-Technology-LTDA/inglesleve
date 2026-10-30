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
import numpy as np
from PIL import Image
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


_BOX_JS = """() => {
  const r = document.querySelector('.talker')?.getBoundingClientRect();
  return r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null;
}"""


def talking(scene: ReelScene, brand: dict) -> bool:
    # A coruja narra a abertura e o fechamento (as cenas do meio mostram o conteúdo).
    return scene.kind in ("hook", "cta") and bool(brand.get("mascot_talk"))


def render_scenes(pack: ContentPack, brand: dict, work: Path, seed: Optional[int]) -> list:
    """[(png, caixa onde a coruja falando entra ou None)]."""
    css = _css(brand, pick_theme(brand, pack, seed), *STORY_SIZE)
    tpl = _env.get_template("reel.html.j2")
    files = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": STORY_SIZE[0], "height": STORY_SIZE[1]})
        for i, scene in enumerate(pack.reel.scenes, 1):
            html = tpl.render(scene=scene, brand=brand, base_css=css, size=_title_size(scene), talk=talking(scene, brand))
            page.set_content(html, wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.evaluate(_AUTOFIT_JS)
            path = work / f"scene_{i:02d}.png"
            page.screenshot(path=str(path))
            files.append((path, page.evaluate(_BOX_JS)))
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


def mouth_states(mp3: Optional[Path], frames: int) -> list:
    """Bico por quadro (0 fechado, 1 meio, 2 aberto) seguindo o volume da fala em PT, que abre a cena."""
    states = [0] * frames
    if not mp3:
        return states
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp3), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True, check=True,
    ).stdout
    pcm = np.frombuffer(raw, np.float32)
    step = 16000 // FPS
    rms = np.array([np.sqrt(np.mean(pcm[j:j + step] ** 2)) for j in range(0, len(pcm) - step, step)])
    if not len(rms):
        return states
    rms = rms / (np.percentile(rms, 95) or 1)
    for f, v in enumerate(rms[:frames]):
        states[f] = 2 if v > 0.55 else (1 if v > 0.2 else 0)
    # sem "piscar" de 1 quadro: um estado isolado repete o anterior
    for f in range(1, frames - 1):
        if states[f - 1] == states[f + 1] != states[f]:
            states[f] = states[f - 1]
    return states


def owl_track(states: list, brand: dict, work: Path, i: int) -> Path:
    """Lista do concat do ffmpeg com as imagens do bico e quanto tempo cada uma fica."""
    root = Path(__file__).resolve().parent.parent
    imgs = [root / p for p in brand["mascot_talk"]]
    lines, run, cur = [], 0, states[0]
    for st in states[1:] + [None]:
        run += 1
        if st != cur:
            lines += [f"file '{imgs[cur]}'", f"duration {run / FPS:.4f}"]
            run, cur = 0, st
    lines.append(f"file '{imgs[states[-1]]}'")  # o concat ignora a duração do último sem isso
    track = work / f"owl_{i:02d}.txt"
    track.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return track


def scene_audio(scene: ReelScene, voices: dict, work: Path, i: int) -> tuple:
    """Narração da cena em WAV, já com a pausa e o respiro final, e o MP3 da fala em PT (ou None)."""
    parts = []
    for lang, text in (("pt", scene.say_pt), ("en", scene.say_en)):
        if text.strip():
            mp3 = work / f"say_{i:02d}_{lang}.mp3"
            _speak(text.strip(), voices[lang], mp3)
            parts.append(mp3)
    total = sum(_duration(p) for p in parts) + GAP * max(len(parts) - 1, 0)
    dur = max(total + TAIL, MIN_SCENE)
    wav = work / f"scene_{i:02d}.wav"
    pt = parts[0] if scene.say_pt.strip() else None
    if not parts:
        _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{dur:.3f}", str(wav))
        return wav, pt
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
    return wav, pt


def scene_clip(png: Path, wav: Path, work: Path, i: int, owl: Optional[tuple] = None) -> Path:
    """owl = (caixa [x, y, w, h], lista do concat com o bico) para a coruja falando."""
    frames = max(int(_duration(wav) * FPS), 1)
    w, h = STORY_SIZE
    extra, base = [], "[0]"
    if owl:
        (bx, by, bw, bh), track = owl
        extra = ["-f", "concat", "-safe", "0", "-i", str(track)]
        base = f"[2]fps={FPS},scale={bw}:{bh}[o];[0][o]overlay={bx}:{by}:shortest=0,"
    # Amplia antes do zoompan para o movimento não "tremer" por arredondamento de pixel.
    video = (
        f"{base}scale={w * 2}:{h * 2},"
        f"zoompan=z='1+{ZOOM}*on/{frames}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={w}x{h}:fps={FPS},"
        "format=yuv420p[v]"
    )
    clip = work / f"clip_{i:02d}.mp4"
    _ffmpeg(
        "-loop", "1", "-framerate", str(FPS), "-i", str(png), "-i", str(wav), *extra,
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
        scenes = render_scenes(pack, brand, work, seed)
        clips = []
        for i, (scene, (png, box)) in enumerate(zip(pack.reel.scenes, scenes), 1):
            wav, pt = scene_audio(scene, voices, work, i)
            owl = None
            if box:
                states = mouth_states(pt, max(int(_duration(wav) * FPS), 1))
                owl = (box, owl_track(states, brand, work, i))
            clips.append(scene_clip(png, wav, work, i, owl))
        listing = work / "clips.txt"
        listing.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
        reel = out_dir / "reel.mp4"
        _ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(reel))
        cover, box = scenes[0]
        if box:  # na capa a coruja aparece parada, de bico aberto (sorrindo)
            img = Image.open(cover).convert("RGBA")
            owl = Image.open(Path(__file__).resolve().parent.parent / brand["mascot_talk"][-1]).convert("RGBA")
            img.alpha_composite(owl.resize((box[2], box[3]), Image.LANCZOS), (box[0], box[1]))
            img.convert("RGB").save(out_dir / "reel_cover.png")
        else:
            shutil.copy(cover, out_dir / "reel_cover.png")
    print(f"Reel de {_duration(reel):.1f}s em {reel}")
    return reel
