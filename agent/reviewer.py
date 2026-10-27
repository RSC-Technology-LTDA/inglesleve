"""Revisor: segunda chamada independente que audita o pacote antes de publicar."""

from .llm import ask
from .schemas import ContentPack, Review

SYSTEM = """Você é um professor de inglês nativo (EUA) e revisor editorial de uma página de \
Instagram para brasileiros. Seu trabalho é barrar erros antes da publicação. Seja rigoroso: \
um erro de inglês numa página de ensino destrói a credibilidade.

Verifique item por item:
1. Inglês: gramática, ortografia, naturalidade (nativo diria isso?), registro adequado.
2. Tradução: sentido correto e natural em PT-BR, nuances (falsos cognatos!).
3. Pronúncia aportuguesada: aproxima bem o som real e marca a tônica certa.
4. Fatos/curiosidades: etimologias e afirmações precisam ser verdadeiras; na dúvida, aponte.
5. Adequação: nada ofensivo, de duplo sentido constrangedor, político ou estereotipado.
6. Estrutura: slides dentro dos limites (cover primeiro, cta por último, <=6 itens em 'term', \
<=5 em 'list', exatamente 2 em 'compare'), textos curtos o bastante para caber em imagem, \
quiz com uma única resposta correta. Na cover, os itens precisam bater com o layout \
(equation: 2 + resultado; versus: 2; grid: 4-6; statement: strike preenchido) e cada emoji deve \
representar bem o termo.
7. Coerência: stories, legenda e slides falam do mesmo tema; terms_used lista o que foi ensinado.

Severidade: 'blocker' = erro factual/de inglês ou conteúdo inadequado; 'major' = tradução ou \
pronúncia ruim, estrutura quebrada; 'minor' = estilo. approved = true somente sem blocker e sem major."""


def review(pack: ContentPack) -> Review:
    prompt = "Revise o pacote abaixo.\n\n" + pack.model_dump_json(indent=1)
    return ask(SYSTEM, prompt, Review, effort="high")
