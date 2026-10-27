"""Renderiza o pacote em PNGs (feed 1080x1350, stories 1080x1920) com Playwright."""

import base64
import re
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from playwright.sync_api import sync_playwright

from . import planner
from .schemas import ContentPack

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
FEED_SIZE = (1080, 1350)
STORY_SIZE = (1080, 1920)

_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))


_LETTER = re.compile(r"^\s*[A-Fa-f]\s*[\)\.:\-]\s+")

_AUTOFIT_JS ="""() => {
  const f = document.querySelector('.frame');
  const c = document.querySelector('.content, .main, .hero');
  let z = 1;
  while (c && f.scrollHeight > f.clientHeight + 1 && z > 0.6) { z -= 0.04; c.style.zoom = z; }
  return z;
}"""

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_css_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False)


def _font_faces() -> str:
    # Fontes embutidas em base64: renderiza igual offline e em CI, sem depender do Google Fonts.
    faces = []
    for family, file in (("Inter", "Inter.ttf"), ("Bricolage Grotesque", "BricolageGrotesque.ttf")):
        data = base64.b64encode((FONTS / file).read_bytes()).decode()
        faces.append(f'@font-face {{ font-family: "{family}"; src: url(data:font/ttf;base64,{data}) format("truetype"); font-weight: 100 900; }}')
    return "\n".join(faces)


def _css(brand: dict, w: int, h: int) -> Markup:
    css = _css_env.get_template("base.css").render(brand=brand, w=w, h=h, font_faces=_font_faces())
    return Markup(css)


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


def render_html(pack: ContentPack, brand: dict) -> List[tuple]:
    """Retorna [(nome_arquivo, html, (w, h))]."""
    pack = _strip_letters(pack)
    pages = []
    label = planner.FORMATS.get(pack.format, {}).get("label", "")
    answers = [s.note for s in pack.feed if s.kind == "quiz" and s.note]
    feed_tpl = _env.get_template("feed.html.j2")
    feed_css = _css(brand, *FEED_SIZE)
    for i, slide in enumerate(pack.feed, 1):
        html = feed_tpl.render(
            slide=slide, pack=pack, brand=brand, base_css=feed_css, index=i, total=len(pack.feed),
            format_label=label, answers=answers if slide.kind == "cta" else [],
        )
        pages.append((f"feed_{i:02d}.png", html, FEED_SIZE))

    story_tpl = _env.get_template("story.html.j2")
    story_css = _css(brand, *STORY_SIZE)
    for i, story in enumerate(pack.stories, 1):
        html = story_tpl.render(story=story, brand=brand, base_css=story_css, index=i, total=len(pack.stories))
        pages.append((f"story_{i:02d}.png", html, STORY_SIZE))
    return pages


def render(pack: ContentPack, brand: dict, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, html, (w, h) in render_html(pack, brand):
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
