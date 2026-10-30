"""Responde os comentários novos dos posts recentes (roda a cada 3 horas no GitHub Actions).

  python comments.py              # responde
  python comments.py --dry-run    # só mostra o que responderia

Só responde comentários ligados ao tema do post; o resto é ignorado sem resposta. Cada comentário
analisado fica em data/comments.json, então nada é respondido duas vezes.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

import metrics
from agent.instagram import Instagram, InstagramError

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "comments.json"
DAYS = 14          # posts mais antigos que isso não são olhados
MAX_REPLIES = 15   # por execução, para nunca parecer robô despejando respostas


def post_content(date: str) -> str:
    """Resumo do que o post ensinou (termos, gabarito), para a resposta bater com o conteúdo."""
    path = ROOT / "output" / date / "pack.json"
    if not date or not path.exists():
        return ""
    pack = json.loads(path.read_text(encoding="utf-8"))
    parts = ["termos: " + ", ".join(pack.get("terms_used", []))]
    for s in pack.get("feed", []):
        if s.get("kind") == "quiz":
            parts.append(f"quiz '{s.get('title')}' → {s.get('note')}")
        elif s.get("kind") in ("compare", "fix", "term", "list"):
            parts.append(" / ".join(f"{i.get('en')} = {i.get('pt')}" for i in s.get("items", [])))
    for st in pack.get("stories", []):
        if st.get("answer"):
            parts.append(f"story '{st.get('headline')}' → {st.get('answer')}")
    return " | ".join(parts)[:3000]


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from agent import replier

    state = metrics.load(STATE_PATH, {})
    ig = Instagram(os.environ["IG_ACCESS_TOKEN"], os.getenv("IG_USER_ID") or None)
    me = ig.account()["username"]
    ours = metrics.our_posts()
    since = datetime.now(timezone.utc) - timedelta(days=DAYS)
    replied = 0
    try:
        for media in ig.recent_media(limit=30):
            if datetime.fromisoformat(media["timestamp"].replace("+0000", "+00:00")) < since:
                continue
            new = [
                c for c in ig.comments(media["id"])
                if c["id"] not in state and c.get("username") != me
                and not any(r.get("username") == me for r in (c.get("replies") or {}).get("data", []))
            ]
            if not new:
                continue
            info = ours.get(media["id"], {})
            post = {"kind": info.get("kind", media.get("media_product_type")), "theme": info.get("theme", ""),
                    "caption": (media.get("caption") or "")[:1500], "content": post_content(info.get("date", ""))}
            for d in replier.decide(post, new):
                comment = next((c for c in new if c["id"] == d.comment_id), None)
                if not comment:
                    continue
                entry = {"media": media["id"], "user": comment.get("username"), "text": comment.get("text"),
                         "action": d.action, "reason": d.reason, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                if d.action == "reply" and d.reply.strip():
                    if replied >= MAX_REPLIES:
                        continue  # fica para a próxima execução
                    print(f"↳ @{comment.get('username')}: {comment.get('text')!r}\n   {d.reply}")
                    if args.dry_run:
                        continue
                    entry["reply"] = d.reply.strip()
                    entry["reply_id"] = ig.reply(comment["id"], d.reply.strip())
                    replied += 1
                else:
                    print(f"  ignorado @{comment.get('username')}: {comment.get('text')!r} ({d.reason})")
                    if args.dry_run:
                        continue
                state[comment["id"]] = entry
    except InstagramError as err:
        if "permission" in str(err).lower() or "(code 10)" in str(err) or "(code 200)" in str(err):
            print("O token não tem instagram_manage_comments; gere de novo com tools/ig_token.py.")
            return 0
        raise
    finally:
        if not args.dry_run:
            metrics.save(STATE_PATH, state)
    print(f"{replied} resposta(s) publicada(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
