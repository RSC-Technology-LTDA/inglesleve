"""Renderiza o pacote em PNGs (feed 1080x1350, stories 1080x1920) com Playwright."""

import base64
import re
import zlib
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from playwright.sync_api import sync_playwright

from . import planner
from .schemas import ContentPack

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
FEED_SIZE = (1080, 1350)
STORY_SIZE = (1080, 1920)

_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))

# Emojis viram ilustrações 3D (Fluent Emoji da Microsoft, licença MIT), baixadas uma vez e guardadas em cache.
EMOJI_DIR = Path(__file__).resolve().parent.parent / "assets" / "emoji"
EMOJI_URL = "https://cdn.jsdelivr.net/gh/shuding/fluentui-emoji-unicode/assets/{}_3d.png"
_HL = re.compile(r"\*([^*]+)\*")


def _emoji_code(ch: str) -> str:
    # Mesmo nome de arquivo do repositório: sem o seletor FE0F, exceto em sequências com ZWJ.
    if "\u200d" not in ch:
        ch = ch.replace("\ufe0f", "")
    return "-".join(f"{ord(c):x}" for c in ch)


@lru_cache(maxsize=None)
def _emoji_data(ch: str) -> Optional[str]:
    code = _emoji_code(ch)
    path = EMOJI_DIR / f"{code}.png"
    if not path.exists():
        try:
            resp = httpx.get(EMOJI_URL.format(code), timeout=20, follow_redirects=True)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200 or not resp.headers.get("content-type", "").startswith("image/"):
            return None  # sem versão 3D (ex: bandeiras): cai no emoji de texto
        EMOJI_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def emoji(ch: str) -> Markup:
    ch = (ch or "").strip()
    if not ch:
        return Markup("")
    data = _emoji_data(ch)
    if data:
        return Markup(f'<img class="e3d" src="{data}" alt="">')
    return Markup('<span class="e3d e3d-txt">') + ch + Markup("</span>")


def highlight(text: str) -> Markup:
    """*palavra* vira <em>palavra</em> (destaque colorido), com o resto escapado."""
    return Markup(_HL.sub(r"<em>\1</em>", str(escape(text or ""))))


_env.globals["emoji"] = emoji
_env.filters["hl"] = highlight


_LETTER = re.compile(r"^\s*[A-Fa-f]\s*[\)\.:\-]\s+")

_AUTOFIT_JS ="""() => {
  const f = document.querySelector('.frame');
  const c = document.querySelector('.content, .main, .hero');
  // Mede pelo último elemento (rodapé/cta): scrollHeight não acusa estouro sobre o padding.
  const limit = f.getBoundingClientRect().bottom - parseFloat(getComputedStyle(f).paddingBottom);
  const over = () => f.lastElementChild.getBoundingClientRect().bottom > limit + 1;
  let z = 1;
  while (c && over() && z > 0.6) { z -= 0.03; c.style.zoom = z; }
  return z;
}"""

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_css_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False)


def _font_faces() -> str:
    # Fontes embutidas em base64: renderiza igual offline e em CI, sem depender do Google Fonts.
    faces = []
    for family, file, weight in (
        ("Inter", "Inter.ttf", "100 900"),
        ("Bricolage Grotesque", "BricolageGrotesque.ttf", "100 900"),
        ("Anton", "Anton.ttf", "400"),
    ):
        data = base64.b64encode((FONTS / file).read_bytes()).decode()
        faces.append(f'@font-face {{ font-family: "{family}"; src: url(data:font/ttf;base64,{data}) format("truetype"); font-weight: {weight}; }}')
    return "\n".join(faces)


def _css(brand: dict, theme: dict, w: int, h: int) -> Markup:
    css = _css_env.get_template("base.css").render(brand=brand, theme=theme, w=w, h=h, font_faces=_font_faces())
    return Markup(css)


def pick_theme(brand: dict, pack: ContentPack, seed: Optional[int] = None) -> dict:
    """Cor de fundo do post. Com seed = dia, posts vizinhos no grid ficam com cores diferentes."""
    themes = brand.get("themes") or [{"name": "paper", "bg": brand["paper"]}]
    if seed is None:
        seed = zlib.crc32(pack.theme.encode())
    return themes[seed % len(themes)]


def _strip_letters(pack: ContentPack) -> ContentPack:
    # O template já mostra A/B/C; remove "A) " caso o modelo tenha colocado no texto.
    pack = pack.model_copy(deep=True)
    for slide in pack.feed:
        if slide.kind == "quiz":
            for it in slide.items:
                it.en = _LETTER.sub("", it.en)
    for story in pack.stories:
        story.options = [_LETTER.sub("", o) for o in story.options]
    return pack


def cover_layout(slide) -> str:
    """Layout pedido pelo redator, ou o escuro se faltar o que ele precisa."""
    emojis = sum(1 for it in slide.items if it.emoji.strip())
    ok = {
        "statement": bool(slide.strike.strip()),
        "equation": len(slide.items) >= 3 and emojis == len(slide.items),
        "versus": len(slide.items) >= 2 and emojis >= 2,
        "grid": len(slide.items) >= 4,
        "hero": emojis >= 1 and bool(slide.items[0].emoji.strip()) if slide.items else False,
    }
    return slide.layout if ok.get(slide.layout) else "dark"


def render_html(pack: ContentPack, brand: dict, seed: Optional[int] = None) -> List[tuple]:
    """Retorna [(nome_arquivo, html, (w, h))]."""
    pack = _strip_letters(pack)
    theme = pick_theme(brand, pack, seed)
    pages = []
    label = planner.FORMATS.get(pack.format, {}).get("label", "")
    answers = [s.note for s in pack.feed if s.kind == "quiz" and s.note]
    feed_tpl = _env.get_template("feed.html.j2")
    feed_css = _css(brand, theme, *FEED_SIZE)
    for i, slide in enumerate(pack.feed, 1):
        html = feed_tpl.render(
            slide=slide, pack=pack, brand=brand, base_css=feed_css, index=i, total=len(pack.feed),
            format_label=label, answers=answers if slide.kind == "cta" else [],
            cover_layout=cover_layout(slide) if slide.kind == "cover" else "",
        )
        pages.append((f"feed_{i:02d}.png", html, FEED_SIZE))

    story_tpl = _env.get_template("story.html.j2")
    story_css = _css(brand, theme, *STORY_SIZE)
    for i, story in enumerate(pack.stories, 1):
        html = story_tpl.render(story=story, brand=brand, base_css=story_css, index=i, total=len(pack.stories))
        pages.append((f"story_{i:02d}.png", html, STORY_SIZE))
    return pages


def render(pack: ContentPack, brand: dict, out_dir: Path, seed: Optional[int] = None) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, html, (w, h) in render_html(pack, brand, seed):
            page = browser.new_page(viewport={"width": w, "height": h})
            page.set_content(html, wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            # Texto longo demais: encolhe o bloco central até caber (mínimo 60%).
            zoom = page.evaluate(_AUTOFIT_JS)
            if zoom < 0.62:
                print(f"  aviso: {name} continua apertado mesmo reduzido; revise o texto")
            if brand.get("keep_html"):
                (out_dir / name.replace(".png", ".html")).write_text(html, encoding="utf-8")
            path = out_dir / name
            page.screenshot(path=str(path), full_page=False)
            page.close()
            files.append(path)
        browser.close()
    return files
