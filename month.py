"""Gera o post extra "Curiosidades do mês" (só carrossel), que sai todo dia 1º.

  python month.py                  # mês de hoje
  python month.py --month 2026-12  # outro mês

Fica em output/mes-<AAAA-MM>/, separado do post do dia, e é publicado com
publish.py noon --dir output/mes-<AAAA-MM>. Stories e Reel já ficam marcados como "skip".
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from agent import planner
from agent.render import render
from agent.schemas import ContentPack

ROOT = Path(__file__).resolve().parent
MAX_ROUNDS = 3
MONTHS = [
    ("janeiro", "January"), ("fevereiro", "February"), ("março", "March"), ("abril", "April"),
    ("maio", "May"), ("junho", "June"), ("julho", "July"), ("agosto", "August"),
    ("setembro", "September"), ("outubro", "October"), ("novembro", "November"), ("dezembro", "December"),
]


def month_dir(first: date) -> Path:
    return ROOT / "output" / f"mes-{first:%Y-%m}"


def skip_all(out: Path, pack: ContentPack) -> None:
    """Só o carrossel vai ao ar: stories e Reel ficam marcados como já tratados."""
    stories = {f"story_{i:02d}.jpg": "skip" for i in range(1, len(pack.stories) + 1)}
    state = {
        "noon": {"carousel": None, "stories": dict(stories)},
        "evening": {"carousel": None, "stories": dict(stories), "reel": "skip"},
    }
    (out / "published.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=date.today().strftime("%Y-%m"), help="AAAA-MM")
    args = ap.parse_args()

    first = date.fromisoformat(args.month + "-01")
    out = month_dir(first)
    if (out / "pack.json").exists():
        print(f"Pacote de {args.month} já existe em {out}; não gera de novo.")
        return 0 if (out / "STATUS").read_text(encoding="utf-8").strip() == "approved" else 2

    from agent import reviewer, writer

    pt, en = MONTHS[first.month - 1]
    extra = (
        f"Mês do post: {pt} de {first.year} ({en} {first.year}). Use as datas reais deste ano nos EUA "
        "(confira o dia da semana de feriados móveis). Não repita curiosidades já usadas em meses anteriores."
    )
    brand = json.loads((ROOT / "brand.json").read_text(encoding="utf-8"))
    history = planner.load_history()
    print(f"{args.month} · Curiosidades do mês ({en})")

    pack, verdict, log = None, None, []
    for round_no in range(1, MAX_ROUNDS + 1):
        print(f"  rodada {round_no}: escrevendo…")
        pack = writer.write(first, "month_facts", history, brand["handle"], feedback=verdict, previous=pack, extra=extra)
        print(f"  rodada {round_no}: revisando…")
        verdict = reviewer.review(pack)
        log.append({"round": round_no, **verdict.model_dump()})
        print(f"    {'aprovado' if verdict.approved else 'reprovado'}: {verdict.summary}")
        if verdict.approved:
            break

    if verdict.approved and verdict.issues:
        from run_daily import polish

        pack, verdict = polish(first, "month_facts", history, brand, pack, verdict, log, extra)

    out.mkdir(parents=True, exist_ok=True)
    pack.reel = None  # só carrossel
    (out / "pack.json").write_text(pack.model_dump_json(indent=2), encoding="utf-8")
    (out / "review.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    hashtags = " ".join("#" + h.lstrip("#") for h in pack.hashtags)
    (out / "caption.txt").write_text(f"{pack.caption}\n\n{hashtags}\n", encoding="utf-8")
    status = "approved" if verdict.approved else "needs_human_review"
    (out / "STATUS").write_text(status + "\n", encoding="utf-8")
    files = render(pack, brand, out, first.toordinal())
    for story in out.glob("story_*.png"):
        story.unlink()  # stories não vão ao ar
    skip_all(out, pack)
    print(f"{len(files)} imagens em {out}")

    if not verdict.approved:
        print("  ATENÇÃO: não passou no revisor; veja review.json. Não será publicado.")
        return 2
    planner.record(first, "month_facts", pack.theme, pack.terms_used, extra=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
