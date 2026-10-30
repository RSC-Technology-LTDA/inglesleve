"""Analista: lê as métricas da semana e sugere o que mudar para converter mais seguidores.

Grava reports/insights-<data>.md (para você ler) e data/insights.json, cujas dicas para o
redator entram no prompt dos próximos posts.
"""

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field

from . import planner
from .llm import ask

ROOT = Path(__file__).resolve().parent.parent
INSIGHTS_PATH = ROOT / "data" / "insights.json"
AUDIENCE_PATH = ROOT / "data" / "audience.json"
REPORTS = ROOT / "reports"


class Recommendation(BaseModel):
    area: Literal["formato", "gancho", "capa", "reel", "stories", "legenda", "horário", "crescimento"]
    change: str = Field(description="O que mudar, concreto e aplicável já na próxima semana")
    why: str = Field(description="Que número sustenta a sugestão (cite posts ou médias)")


class Insights(BaseModel):
    summary: str = Field(description="3-5 linhas: crescimento da semana e o que mais trouxe seguidores")
    best: List[str] = Field(description="Os 3 posts que mais converteram, como 'data · tipo · tema: motivo'")
    worst: List[str] = Field(description="Os 2-3 que menos converteram e o provável motivo")
    recommendations: List[Recommendation] = Field(description="3 a 6 sugestões, da mais para a menos importante")
    writer_tips: List[str] = Field(description="Até 5 regras curtas para o redator aplicar nos próximos posts")
    experiment: str = Field(description="Um teste A/B simples para a próxima semana e como medir")


SYSTEM = """Você é analista de crescimento de uma página de Instagram que ensina inglês para brasileiros \
(@inglesleve.br). Todo dia sai um carrossel (12h), stories (12h e 18h) e um Reel (18h), gerados por IA \
com um formato por dia da semana. O objetivo é chegar a 1 milhão de seguidores: a métrica que mais \
importa é seguidores ganhos por alcance (conversão); depois compartilhamentos e salvamentos (que \
levam o post a não seguidores) e retenção nos Reels.

Analise os números com honestidade: com poucos dados, diga que a amostra é pequena e não invente \
padrões. Compare formatos, ganchos e tipos de post. Sugestões precisam ser concretas (o que escrever, \
que formato repetir, que gancho testar), não genéricas ("poste com consistência"). As writer_tips \
viram instruções para o redator: escreva como regra curta e acionável, que valha para qualquer formato \
(o formato de cada dia continua mandando na estrutura).
Contexto: a publicação automática começou em 29/10/2026; posts anteriores (e os de kind 'manual') foram \
feitos à mão. Alguns posts são extras, fora do calendário de formatos.
Limites da publicação automática (não sugira o que ela não faz): stories saem só como imagem, sem \
figurinhas (enquete, quiz, link, menção, repost de Reel), então a interação é por resposta no DM; \
o total de seguidores é gravado todo dia às 18h e as métricas dos posts são atualizadas nessa coleta (os dos últimos \
dias ainda estão amadurecendo). Sugestões que dependem de ação manual (collab, responder comentários) \
são bem-vindas, mas marque-as como manuais."""


def _rate(n, d):
    return round(1000 * n / d, 1) if n is not None and d else None


def table(data: dict, day: date, days: int = 28) -> dict:
    """Resumo dos posts recentes e médias por formato e tipo, para caber no prompt."""
    since = (day - timedelta(days=days)).isoformat()
    rows, groups = [], defaultdict(list)
    for media_id, m in data["media"].items():
        # Dia real em que foi ao ar (posts extras usam pastas de outras datas).
        when = (m.get("timestamp") or "")[:10] or m.get("date") or ""
        if when < since:
            continue
        ins = m.get("insights", {})
        reach = ins.get("reach")
        row = {
            "date": when, "kind": m.get("kind"), "format": m.get("format"), "theme": m.get("theme"),
            "hook": m.get("hook") or m.get("caption", "")[:80], "likes": m.get("like_count"),
            "comments": m.get("comments_count"), **ins,
            "follows_per_1k_reach": _rate(ins.get("follows"), reach),
            "shares_per_1k_reach": _rate(ins.get("shares"), reach),
            "saves_per_1k_reach": _rate(ins.get("saved"), reach),
        }
        rows.append(row)
        groups[(m.get("kind"), m.get("format"))].append(row)
    averages = []
    for (kind, fmt), rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        avg = {"kind": kind, "format": fmt, "posts": len(rs)}
        for key in ("reach", "views", "follows", "shares", "saved", "likes", "comments"):
            vals = [r[key] for r in rs if isinstance(r.get(key), (int, float))]
            avg[key] = round(sum(vals) / len(vals), 1) if vals else None
        averages.append(avg)
    return {"posts": sorted(rows, key=lambda r: r["date"]), "averages": averages}


def build_prompt(data: dict, day: date) -> str:
    followers = data["followers"][-60:]
    formats = {k: {"dia": v["weekday"], "nome": v["label"], "reel": v.get("series")} for k, v in planner.FORMATS.items()}
    previous = json.loads(INSIGHTS_PATH.read_text(encoding="utf-8")) if INSIGHTS_PATH.exists() else None
    parts = [
        f"Data: {day.isoformat()}",
        "Seguidores por dia:\n" + json.dumps(followers, ensure_ascii=False),
        "Formatos (dia 0 = segunda):\n" + json.dumps(formats, ensure_ascii=False),
        "Posts das últimas 4 semanas e médias por tipo/formato:\n" + json.dumps(table(data, day), ensure_ascii=False, indent=1),
    ]
    audience = _audience()
    if audience:
        short = {k: dict(list(v.items())[:10]) for k, v in audience.items() if isinstance(v, dict)}
        parts.append("Quem segue a página (top 10 de cada; estado somado das 45 maiores cidades):\n" + json.dumps(short, ensure_ascii=False))
    if previous:
        parts.append("Análise anterior (veja se as sugestões funcionaram):\n" + json.dumps(previous, ensure_ascii=False))
    return "\n\n".join(parts)


def _audience() -> dict:
    return json.loads(AUDIENCE_PATH.read_text(encoding="utf-8")) if AUDIENCE_PATH.exists() else {}


def audience_markdown(audience: dict) -> List[str]:
    """Tabelas de público, calculadas direto dos números (sem passar pelo modelo)."""
    if not audience:
        return []
    names = {"country": "País", "state": "Estado", "city": "Cidade", "age": "Idade", "gender": "Gênero"}
    labels = {"F": "Mulheres", "M": "Homens", "U": "Não informado"}
    lines = ["## Quem segue a página", ""]
    for key in ("country", "state", "city", "age", "gender"):
        values = audience.get(key, {})
        rows, total = list(values.items())[:10], sum(values.values())
        if not rows:
            continue
        lines += [f"**{names[key]}**", "", f"| {names[key]} | Seguidores | % |", "|---|---:|---:|"]
        lines += [f"| {labels.get(k, k) if key == 'gender' else k} | {v} | {100 * v / total:.0f}% |" for k, v in rows]
        lines.append("")
    lines += ["% sobre os seguidores com o dado informado. Estado e cidade cobrem só as 45 cidades com mais "
              "seguidores (limite da API).", ""]
    return lines


def to_markdown(ins: Insights, day: date, data: dict) -> str:
    f = data["followers"]
    week = [x for x in f if x["date"] >= (day - timedelta(days=7)).isoformat()]
    growth = f"{f[-1]['followers']} seguidores" + (f" (+{f[-1]['followers'] - week[0]['followers']} em 7 dias)" if len(week) > 1 else "")
    lines = [f"# Análise de {day.strftime('%d/%m/%Y')}", "", f"**{growth}**", "", ins.summary, "", "## O que mais converteu"]
    lines += [f"- {b}" for b in ins.best]
    lines += ["", "## O que menos converteu"] + [f"- {w}" for w in ins.worst]
    lines += ["", "## Sugestões"]
    lines += [f"{i}. **[{r.area}] {r.change}**  \n   {r.why}" for i, r in enumerate(ins.recommendations, 1)]
    lines += ["", "## Já aplicado no redator", *[f"- {t}" for t in ins.writer_tips], "", "## Teste da semana", ins.experiment, ""]
    lines += audience_markdown(_audience())
    return "\n".join(lines)


def run(data: dict, day: date) -> Path:
    ins = ask(SYSTEM, build_prompt(data, day), Insights)
    INSIGHTS_PATH.write_text(json.dumps({"date": day.isoformat(), **ins.model_dump()}, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"insights-{day.isoformat()}.md"
    path.write_text(to_markdown(ins, day, data), encoding="utf-8")
    return path


def writer_tips() -> List[str]:
    if not INSIGHTS_PATH.exists():
        return []
    return json.loads(INSIGHTS_PATH.read_text(encoding="utf-8")).get("writer_tips", [])[:5]


def top_themes(n: int = 4) -> List[str]:
    """Temas dos posts que mais trouxeram seguidores (ou salvamentos/curtidas, sem métricas completas)."""
    path = ROOT / "data" / "metrics.json"
    if not path.exists():
        return []
    best = {}
    for m in json.loads(path.read_text(encoding="utf-8"))["media"].values():
        if m.get("kind") not in ("carousel", "reel") or not m.get("theme"):
            continue
        ins = m.get("insights", {})
        score = (ins.get("follows") or 0, ins.get("saved") or 0, ins.get("shares") or 0, m.get("like_count") or 0)
        best[m["theme"]] = max(best.get(m["theme"], score), score)
    return [t for t, _ in sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:n]]
