"""Coleta métricas da conta e dos posts e marca as metas de seguidores atingidas.

  python metrics.py            # salva em data/metrics.json e data/milestones.json
  python metrics.py --report   # também roda o analista e grava reports/insights-<data>.md

Cada post publicado pelo agente é ligado ao pacote que o gerou (formato, tema, gancho), para o
analista comparar o que converte melhor. Stories só têm métricas nas 24h em que estão no ar,
então a coleta roda todo dia às 18h.
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from agent.instagram import Instagram, InstagramError

ROOT = Path(__file__).resolve().parent
METRICS_PATH = ROOT / "data" / "metrics.json"
MILESTONES_PATH = ROOT / "data" / "milestones.json"
MILESTONES = [1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def our_posts() -> dict:
    """id da mídia → o que o agente publicou (data, tipo, formato, tema, gancho)."""
    posts = {}
    for state_file in sorted((ROOT / "output").glob("*/published.json")):
        out = state_file.parent
        try:
            pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        base = {"date": out.name, "format": pack.get("format"), "theme": pack.get("theme")}
        cover = (pack.get("feed") or [{}])[0]
        reel = pack.get("reel") or {}
        for slot in load(state_file, {}).values():
            if not isinstance(slot, dict):
                continue
            if slot.get("carousel"):
                posts[slot["carousel"]] = {**base, "kind": "carousel", "hook": cover.get("title", "")}
            if slot.get("reel"):
                hook = (reel.get("scenes") or [{}])[0].get("title", "")
                posts[slot["reel"]] = {**base, "kind": "reel", "hook": hook}
            for name, media_id in (slot.get("stories") or {}).items():
                i = int(name.split("_")[1].split(".")[0]) - 1
                story = (pack.get("stories") or [])[i] if i < len(pack.get("stories") or []) else {}
                posts[media_id] = {**base, "kind": "story", "story_kind": story.get("kind"), "hook": story.get("headline", "")}
    return posts


def collect(ig: Instagram, today: date) -> dict:
    data = load(METRICS_PATH, {"followers": [], "media": {}})
    account = ig.account()
    data["followers"] = [f for f in data["followers"] if f["date"] != today.isoformat()]
    data["followers"].append({"date": today.isoformat(), "followers": account["followers_count"], "media": account["media_count"]})
    print(f"@{account['username']}: {account['followers_count']} seguidores, {account['media_count']} posts")

    ours = our_posts()
    items = [(m, m.get("media_product_type", "FEED")) for m in ig.recent_media()]
    items += [({**s, "media_product_type": "STORY"}, "STORY") for s in ig.live_stories()]
    no_insights = False
    for m, kind in items:
        entry = data["media"].setdefault(m["id"], {})
        entry.update({k: m[k] for k in ("permalink", "timestamp", "media_type", "like_count", "comments_count") if k in m})
        entry["product"] = kind
        entry["caption"] = (m.get("caption") or "")[:120]
        entry.update(ours.get(m["id"], {"kind": "manual"}))
        if not no_insights:
            try:
                entry["insights"] = ig.media_insights(m["id"], kind)
            except InstagramError as err:
                if "permission" in str(err).lower() or "(code 10)" in str(err) or "(code 200)" in str(err):
                    no_insights = True
                    print("aviso: o token não tem instagram_manage_insights; coletando só seguidores, curtidas e comentários")
                else:
                    print(f"aviso: sem métricas para {m['id']}: {err}")
        entry["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save(METRICS_PATH, data)
    print(f"{len(items)} posts atualizados em {METRICS_PATH.relative_to(ROOT)}")
    return data


def check_milestones(followers: int, today: date) -> list:
    """Meta nova atingida → fica 'pending' até o post comemorativo sair."""
    state = load(MILESTONES_PATH, {})
    new = []
    for m in MILESTONES:
        if followers >= m and str(m) not in state:
            # Na primeira coleta, metas que já tinham passado não ganham post atrasado.
            state[str(m)] = {"reached": today.isoformat(), "status": "pending" if m == max(x for x in MILESTONES if x <= followers) else "skipped"}
            new.append(m)
    if new:
        save(MILESTONES_PATH, state)
        print("meta atingida: " + ", ".join(f"{m:,}".replace(",", ".") for m in new))
    return new


def pending_milestone() -> int:
    state = load(MILESTONES_PATH, {})
    pending = [int(m) for m, v in state.items() if v.get("status") == "pending"]
    return max(pending) if pending else 0


def reached_milestone() -> int:
    """Maior meta já atingida (para forçar o comemorativo com --format milestone)."""
    state = load(MILESTONES_PATH, {})
    return max((int(m) for m in state), default=MILESTONES[0])


def mark_celebrated(milestone: int, day: date) -> None:
    state = load(MILESTONES_PATH, {})
    if str(milestone) in state:
        state[str(milestone)].update(status="celebrated", post_date=day.isoformat())
        save(MILESTONES_PATH, state)


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat, default=date.today())
    ap.add_argument("--report", action="store_true", help="roda o analista depois da coleta")
    args = ap.parse_args()

    ig = Instagram(os.environ["IG_ACCESS_TOKEN"], os.getenv("IG_USER_ID") or None)
    data = collect(ig, args.date)
    check_milestones(data["followers"][-1]["followers"], args.date)
    if args.report:
        from agent import analyst

        path = analyst.run(data, args.date)
        print(f"relatório em {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
