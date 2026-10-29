"""Publica o pacote do dia no Instagram.

  python publish.py prepare --date 2026-10-28
      Converte os PNGs do dia para JPEG (formato exigido pela API) em output/<data>/jpg/.

  python publish.py noon --base-url https://raw.githubusercontent.com/<repo>/<sha>
      12h: carrossel + stories de pergunta/dica/desafio. Só publica se STATUS = approved.

  python publish.py evening --base-url ...
      18h: story(s) de resposta.

--dry-run confere arquivos e URLs sem publicar. O que já foi publicado fica em
output/<data>/published.json, então rodar de novo não duplica posts.
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv
from PIL import Image

from agent.instagram import Instagram
from agent.schemas import ContentPack

ROOT = Path(__file__).resolve().parent
CAPTION_LIMIT = 2200


def day_dir(day: date) -> Path:
    return ROOT / "output" / day.isoformat()


def prepare(out: Path) -> list:
    jpg_dir = out / "jpg"
    jpg_dir.mkdir(exist_ok=True)
    files = []
    for png in sorted(out.glob("*.png")):
        jpg = jpg_dir / f"{png.stem}.jpg"
        Image.open(png).convert("RGB").save(jpg, "JPEG", quality=92, optimize=True)
        files.append(jpg)
    print(f"{len(files)} JPEGs em {jpg_dir}")
    return files


def load_state(out: Path) -> dict:
    path = out / "published.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(out: Path, state: dict) -> None:
    (out / "published.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def url_for(base_url: str, out: Path, name: str) -> str:
    rel = (out / "jpg" / name).relative_to(ROOT).as_posix()
    return f"{base_url.rstrip('/')}/{rel}"


def wait_reachable(urls: list, attempts: int = 12) -> None:
    # O raw.githubusercontent.com pode levar alguns segundos para servir arquivos recém-enviados.
    pending = list(urls)
    for _ in range(attempts):
        pending = [u for u in pending if httpx.head(u, follow_redirects=True, timeout=20).status_code != 200]
        if not pending:
            return
        time.sleep(5)
    raise SystemExit("URLs inacessíveis (o repositório é público?):\n" + "\n".join(pending))


def story_names(pack: ContentPack, evening: bool) -> list:
    return [f"story_{i:02d}.jpg" for i, s in enumerate(pack.stories, 1) if (s.kind == "answer") == evening]


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("slot", choices=["prepare", "noon", "evening"])
    ap.add_argument("--date", type=date.fromisoformat, default=date.today())
    ap.add_argument("--base-url", default=os.getenv("MEDIA_BASE_URL"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = day_dir(args.date)
    if not (out / "pack.json").exists():
        print(f"Sem pacote em {out}; rode run_daily.py antes.")
        return 1
    if args.slot == "prepare":
        prepare(out)
        return 0

    status = (out / "STATUS").read_text(encoding="utf-8").strip()
    if status != "approved":
        print(f"STATUS = {status}: não publico. Revise {out / 'review.json'}.")
        return 2
    if not args.base_url:
        print("Falta --base-url (ou MEDIA_BASE_URL).")
        return 1

    pack = ContentPack.model_validate_json((out / "pack.json").read_text(encoding="utf-8"))
    state = load_state(out)
    slot_state = state.setdefault(args.slot, {"carousel": None, "stories": {}})

    feed = [f"feed_{i:02d}.jpg" for i in range(1, len(pack.feed) + 1)] if args.slot == "noon" else []
    stories = story_names(pack, evening=args.slot == "evening")
    caption = (out / "caption.txt").read_text(encoding="utf-8").strip()
    if len(caption) > CAPTION_LIMIT:
        print(f"Legenda com {len(caption)} caracteres; o limite é {CAPTION_LIMIT}.")
        return 1

    missing = [n for n in feed + stories if not (out / "jpg" / n).exists()]
    if missing:
        print(f"Faltam JPEGs (rode 'publish.py prepare'): {missing}")
        return 1

    todo_feed = feed if feed and not slot_state["carousel"] else []
    todo_stories = [n for n in stories if n not in slot_state["stories"]]
    urls = [url_for(args.base_url, out, n) for n in todo_feed + todo_stories]
    if not urls:
        print(f"Nada a publicar no horário '{args.slot}' (já publicado ou sem itens).")
        return 0
    wait_reachable(urls)

    ig = Instagram(os.environ["IG_ACCESS_TOKEN"], os.getenv("IG_USER_ID") or None)
    if args.dry_run:
        # Confere também se o token vale e aponta para a conta certa.
        user = ig._call("GET", ig.user_id, fields="username")
        print(f"Token OK para @{user['username']}. dry-run, publicaria:\n" + "\n".join(urls))
        return 0

    try:
        if todo_feed:
            media_id = ig.publish_carousel([url_for(args.base_url, out, n) for n in todo_feed], caption)
            slot_state["carousel"] = media_id
            print(f"carrossel publicado: {media_id}")
        for name in todo_stories:
            # Salva depois de cada mídia: se algo falhar no meio, a próxima execução não duplica.
            slot_state["stories"][name] = ig.publish_story(url_for(args.base_url, out, name))
            print(f"story publicado: {name}")
    finally:
        save_state(out, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
