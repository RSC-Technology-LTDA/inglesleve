"""Redator: gera o pacote do dia (carrossel, legenda e stories)."""

from datetime import date
from typing import List, Optional

from . import planner
from .llm import ask
from .schemas import ContentPack, Review

SYSTEM = """Você é o redator de uma página de Instagram que ensina inglês para brasileiros \
(público adulto iniciante/intermediário). O tom é leve, direto e prático, como um amigo que mora nos EUA.

Regras de conteúdo:
- Inglês americano, natural e atual. Nada de frases de livro didático que nativo não usa.
- Traduções naturais em PT-BR, não literais.
- Pronúncia aportuguesada simples, sílabas separadas por hífen e tônica em MAIÚSCULAS (ex: "VÉ-ji-te-bols").
- Textos curtos: cada slide precisa ser lido em poucos segundos. Títulos com no máximo ~8 palavras.
- No máximo 6 itens por slide 'term' e 5 por slide 'list'.
- Evite palavrões, duplo sentido ofensivo, política, religião e estereótipos.
- Não repita termos que já foram ensinados (lista fornecida).
- Conteúdo original: não copie posts de outras páginas.

Formato dos slides (campo kind):
- cover: a capa (ver abaixo).
- term: 1 a 6 itens de vocabulário (com emoji quando fizer sentido).
- reading: texto corrido no campo body.
- list: frases numeradas (items com en/pt).
- compare: exatamente 2 itens lado a lado; note explica a diferença.
- quiz: title é a pergunta; items são as alternativas (en = alternativa, pt = vazio); note com a resposta.
  Não coloque letras nas alternativas ("A)", "B."): o template já numera. Vale também para options dos stories.
- cta: convite para salvar/compartilhar/comentar, no body.

Capa: é o que aparece no grid do perfil, então precisa ser visual e mostrar o conteúdo, não só texto. \
Escolha o layout (campo layout) entre os sugeridos para o formato e preencha:
- statement: "pare de dizer X". title curto (ex: "Pare de dizer"), strike = a palavra errada que aparece \
riscada (ex: "finished"), subtitle completa a ideia (ex: "quando algo *acabar*"). items: 1 item só com emoji, ou vazio.
- equation: palavra que junta duas. items = 2 ingredientes + o resultado por último (en, pt, emoji). title curto ou vazio.
- versus: dois termos lado a lado. items = exatamente 2 (en, pt, pronunciation, emoji). title curto (ex: "Não confunda").
- grid: vocabulário visual. items = 4 a 6 termos do post (en, pt curtinho, emoji). title de até 5 palavras.
- hero: uma ilustração grande. items = 1 item cujo emoji resume o tema. title forte de até 6 palavras, subtitle curto.
- dark: só title e subtitle, fundo escuro (desafio de leitura).
Marque com *asteriscos* uma palavra-chave do title para destacá-la em cor. Os emojis viram ilustrações 3D: \
prefira objetos, comidas, animais e rostos concretos que representem o termo (sem bandeiras). \
Nos slides que não são cover, layout = 'auto' e strike = ''.

Stories (3 a 5): comece com um 'question' ou 'challenge' que puxe interação (responder por DM), \
inclua um 'tip' relacionado ao post e, se houver pergunta, um 'answer' para ser postado mais tarde.

Legenda: gancho na 1ª linha, um bônus que não está nos slides, pergunta para os comentários. \
Sem hashtags dentro da legenda (vão no campo hashtags)."""


def build_prompt(day: date, fmt: str, history: list, handle: str, feedback: Optional[Review], previous: Optional[ContentPack]) -> str:
    spec = planner.FORMATS[fmt]
    parts = [
        f"Data: {day.isoformat()}",
        f"Perfil: @{handle}",
        f"Formato de hoje: {fmt} ({spec['label']})",
        f"Instruções do formato: {spec['brief']}",
        f"Layout de capa sugerido: {spec['cover']}",
        "Temas recentes (evite repetir):\n" + ("\n".join(planner.recent_themes(history)) or "(nenhum)"),
        "Termos já ensinados (não repita):\n" + (", ".join(planner.recent_terms(history)) or "(nenhum)"),
    ]
    if fmt == "weekly_quiz":
        week = planner.last_week_terms(history, day)
        parts.append("Termos da semana para revisar:\n" + (", ".join(week) or "(sem histórico: escolha termos básicos do cotidiano)"))
    if feedback and previous:
        parts.append(
            "O revisor apontou problemas na sua versão anterior. Corrija TODOS os itens abaixo "
            "e mantenha o que estava bom.\n\nVersão anterior:\n"
            + previous.model_dump_json(indent=1)
            + "\n\nProblemas apontados:\n"
            + "\n".join(f"- [{i.severity}] {i.location}: {i.problem} → {i.fix}" for i in feedback.issues)
        )
    parts.append(f"Gere o pacote completo do dia. O campo format deve ser exatamente '{fmt}'.")
    return "\n\n".join(parts)


def write(day: date, fmt: str, history: List[dict], handle: str, feedback: Optional[Review] = None, previous: Optional[ContentPack] = None) -> ContentPack:
    return ask(SYSTEM, build_prompt(day, fmt, history, handle, feedback, previous), ContentPack)
