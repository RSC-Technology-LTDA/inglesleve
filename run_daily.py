"""Gera o pacote de conteúdo do dia: redator → revisor (até N rodadas) → PNGs.

Uso:
  python run_daily.py                      # hoje, formato do dia da semana
  python run_daily.py --date 2026-10-28    # outra data
  python run_daily.py --format idiom       # força um formato
  python run_daily.py --from-json samples/sample_pack.json   # só renderiza (sem API)
  python run_daily.py --polish             # aplica os ajustes do revisor ao pacote do dia
  python run_daily.py --add-reel           # escreve só o Reel de um pacote que ainda não tem
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from agent import planner
from agent.reel import render_reel
from agent.render import render
from agent.schemas import ContentPack

ROOT = Path(__file__).resolve().parent
MAX_ROUNDS = 3


def out_seed(out: Path):
    try:
        return date.fromisoformat(out.name).toordinal()  # cor do post muda a cada dia
    except ValueError:
        return None


def write_outputs(out: Path, pack: ContentPack, review_log: list, status: str, brand: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "pack.json").write_text(pack.model_dump_json(indent=2), encoding="utf-8")
    (out / "review.json").write_text(json.dumps(review_log, ensure_ascii=False, indent=2), encoding="utf-8")
    hashtags = " ".join("#" + h.lstrip("#") for h in pack.hashtags)
    (out / "caption.txt").write_text(f"{pack.caption}\n\n{hashtags}\n", encoding="utf-8")
    (out / "STATUS").write_text(status + "\n", encoding="utf-8")
    seed = out_seed(out)
    files = render(pack, brand, out, seed)
    print(f"{len(files)} imagens em {out}")
    try:
        render_reel(pack, brand, out, seed)
    except Exception as e:  # sem Reel o resto do dia continua valendo
        print(f"  aviso: não consegui montar o Reel ({e})")


def polish(day, fmt, history, brand, pack, verdict, log):
    """Pacote aprovado com ajustes 'minor': aplica uma vez e só fica com a versão nova se ela também for aprovada."""
    from agent import reviewer, writer

    print(f"  polimento: aplicando {len(verdict.issues)} ajuste(s) do revisor…")
    revised = writer.write(day, fmt, history, brand["handle"], feedback=verdict, previous=pack)
    new_verdict = reviewer.review(revised)
    log.append({"round": "polish", **new_verdict.model_dump()})
    if new_verdict.approved:
        print(f"    aprovado: {new_verdict.summary}")
        return revised, new_verdict
    print("    versão polida reprovada; mantendo a anterior")
    return pack, verdict


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat, default=date.today())
    ap.add_argument("--format", choices=list(planner.FORMATS))
    ap.add_argument("--from-json", type=Path, help="Renderiza um pack.json existente, sem chamar a API")
    ap.add_argument("--polish", action="store_true", help="Aplica os ajustes do revisor ao pacote já gerado nessa data")
    ap.add_argument("--add-reel", action="store_true", help="Escreve e monta só o Reel do pacote já gerado nessa data")
    ap.add_argument("--out", type=Path, default=ROOT / "output")
    args = ap.parse_args()

    brand = json.loads((ROOT / "brand.json").read_text(encoding="utf-8"))
    out = args.out / args.date.isoformat()

    if args.polish:
        from agent.schemas import Review

        pack = ContentPack.model_validate_json((out / "pack.json").read_text(encoding="utf-8"))
        log = json.loads((out / "review.json").read_text(encoding="utf-8"))
        verdict = Review.model_validate({k: v for k, v in log[-1].items() if k != "round"})
        if not verdict.issues:
            print("Nada para polir.")
            return 0
        pack, verdict = polish(args.date, pack.format, planner.load_history(), brand, pack, verdict, log)
        write_outputs(out, pack, log, "approved" if verdict.approved else "needs_human_review", brand)
        if verdict.approved:
            planner.record(args.date, pack.format, pack.theme, pack.terms_used)
        return 0 if verdict.approved else 2

    if args.add_reel:
        from agent import writer

        pack = ContentPack.model_validate_json((out / "pack.json").read_text(encoding="utf-8"))
        pack.reel = writer.write_reel(pack)
        (out / "pack.json").write_text(pack.model_dump_json(indent=2), encoding="utf-8")
        return 0 if render_reel(pack, brand, out, out_seed(out)) else 1

    if args.from_json:
        pack = ContentPack.model_validate_json(args.from_json.read_text(encoding="utf-8"))
        write_outputs(out, pack, [], "rendered_from_json", brand)
        return 0

    from agent import reviewer, writer  # importa o SDK só quando vai usar a API

    fmt = args.format or planner.format_for(args.date)
    history = planner.load_history()
    print(f"{args.date} · formato: {fmt}")

    pack, verdict, log = None, None, []
    for round_no in range(1, MAX_ROUNDS + 1):
        print(f"  rodada {round_no}: escrevendo…")
        pack = writer.write(args.date, fmt, history, brand["handle"], feedback=verdict, previous=pack)
        print(f"  rodada {round_no}: revisando…")
        verdict = reviewer.review(pack)
        log.append({"round": round_no, **verdict.model_dump()})
        print(f"    {'aprovado' if verdict.approved else 'reprovado'}: {verdict.summary}")
        if verdict.approved:
            break

    if verdict.approved and verdict.issues:
        pack, verdict = polish(args.date, fmt, history, brand, pack, verdict, log)

    status = "approved" if verdict.approved else "needs_human_review"
    write_outputs(out, pack, log, status, brand)
    if verdict.approved:
        planner.record(args.date, fmt, pack.theme, pack.terms_used)
    else:
        print("  ATENÇÃO: não passou no revisor; veja review.json antes de publicar.")
    return 0 if verdict.approved else 2


if __name__ == "__main__":
    sys.exit(main())
