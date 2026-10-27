"""Gera opções de foto de perfil (1080x1080) nas cores e fontes da marca.

Uso: .venv/bin/python tools/profile_pics.py
Saída: assets/profile/*.png e assets/profile/preview.png (como aparece em círculo, em vários tamanhos).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from agent.render import _font_faces  # noqa: E402

OUT = ROOT / "assets" / "profile"
B = json.loads((ROOT / "brand.json").read_text(encoding="utf-8"))
INK, PAPER, ACCENT, TEAL = B["ink"], B["paper"], B["accent"], B["accent_2"]

# Cada design é um SVG 1080x1080; o Instagram corta em círculo, então o essencial fica no centro.
DESIGNS = {
    # Balão de fala que flutua como um balão de festa: "leve" no sentido literal.
    "leve_balao": f"""
      <rect width="1080" height="1080" fill="{TEAL}"/>
      <path d="M540 760 Q520 840 560 900 Q600 960 570 1040" fill="none" stroke="{INK}" stroke-width="18" stroke-linecap="round"/>
      <path d="M190 330 Q190 210 310 210 H770 Q890 210 890 330 V600 Q890 720 770 720 H600 L540 790 L480 720 H310 Q190 720 190 600 Z" fill="{PAPER}"/>
      <text x="540" y="345" text-anchor="middle" font-family="Inter" font-weight="800" font-size="78" fill="{ACCENT}" letter-spacing="10">INGLÊS</text>
      <text x="540" y="590" text-anchor="middle" font-family="Bricolage Grotesque" font-weight="800" font-size="270" fill="{INK}" letter-spacing="-10">leve</text>
    """,
    # Wordmark simples em duas linhas, máxima leitura em tamanho pequeno.
    "leve_wordmark": f"""
      <rect width="1080" height="1080" fill="{ACCENT}"/>
      <circle cx="540" cy="540" r="390" fill="{PAPER}"/>
      <text x="540" y="470" text-anchor="middle" font-family="Inter" font-weight="800" font-size="110" fill="{INK}" letter-spacing="8">INGLÊS</text>
      <text x="540" y="700" text-anchor="middle" font-family="Bricolage Grotesque" font-weight="800" font-size="250" fill="{TEAL}" letter-spacing="-10">leve</text>
    """,
}


def page_html(svg: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_font_faces()}
      html,body{{margin:0;width:1080px;height:1080px;overflow:hidden}}</style></head>
      <body><svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">{svg}</svg></body></html>"""


def preview_html(names) -> str:
    # Cada opção em círculo, nos tamanhos do perfil (180px), do feed (56px) e dos stories (32px).
    rows = "".join(
        f"""<div class="row"><img src="{n}.png" style="width:180px"><img src="{n}.png" style="width:56px">
        <img src="{n}.png" style="width:32px"><span>{n}</span></div>"""
        for n in names
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_font_faces()}
      body{{margin:0;padding:32px;background:#fff;font-family:Inter;width:720px}}
      .row{{display:flex;align-items:center;gap:28px;margin-bottom:24px}}
      img{{border-radius:50%;border:1px solid #ddd}} span{{font-size:22px;font-weight:600;color:#333}}
    </style></head><body>{rows}</body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        for name, svg in DESIGNS.items():
            page.set_content(page_html(svg))
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(OUT / f"{name}.png"))
        (OUT / "preview.html").write_text(preview_html(DESIGNS), encoding="utf-8")
        page.set_viewport_size({"width": 784, "height": 100})
        page.goto((OUT / "preview.html").as_uri())
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(OUT / "preview.png"), full_page=True)
        (OUT / "preview.html").unlink()
        browser.close()
    print(f"{len(DESIGNS)} opções em {OUT}")


if __name__ == "__main__":
    main()
