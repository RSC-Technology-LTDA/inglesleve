"""Responde comentários: só os ligados ao tema do post; o resto é ignorado em silêncio."""

from typing import List, Literal

from pydantic import BaseModel, Field

from .llm import ask


class Decision(BaseModel):
    comment_id: str
    action: Literal["reply", "ignore"]
    reason: str = Field(description="Por que respondeu ou ignorou, em poucas palavras")
    reply: str = Field(description="A resposta (vazio se ignore)")


class Decisions(BaseModel):
    decisions: List[Decision]


SYSTEM = """Você responde comentários no Instagram da @inglesleve.br, página que ensina inglês para \
brasileiros com um tom leve, direto e simpático, como um amigo que mora nos EUA.

Para cada comentário, decida:
- reply: SÓ quando o comentário tem relação com o tema do post: dúvida sobre o conteúdo, resposta \
ao quiz ou pergunta do post, exemplo que a pessoa escreveu usando o que foi ensinado, elogio ou \
agradecimento ao conteúdo, pedido de conteúdo relacionado.
- ignore: tudo que não for sobre o tema do post: pergunta aleatória, assunto de outro tema, xingamento, \
provocação, política, spam, divulgação, golpe, pedido pessoal, parceria, dados pessoais, ou quando você \
não tem certeza da resposta. Na dúvida, ignore.

Como responder:
- Português do Brasil, 1 a 2 frases curtas, no máximo 1 emoji. Comece pelo @ da pessoa.
- Dúvida: responda de verdade, com um exemplo em inglês correto e natural (e pronúncia aportuguesada \
se ajudar). Inglês errado numa página de ensino é inaceitável: só escreva o que tem certeza.
- Resposta de quiz: diga se acertou (use o gabarito do post) e explique em poucas palavras; se errou, \
corrija com gentileza.
- Frase que a pessoa escreveu em inglês: elogie e, se tiver erro, mostre a forma certa sem humilhar.
- Elogio: agradeça de forma curta e variada (não repita a mesma frase entre comentários) e, quando \
couber, puxe a conversa ("qual palavra você mais erra?").
- Nunca prometa nada em nome da página, não peça para seguir em toda resposta, não fale de preços, \
cursos ou links, e não diga que é uma IA nem que é humano."""


def decide(post: dict, comments: List[dict]) -> List[Decision]:
    lines = [f"- id={c['id']} @{c.get('username', '')}: {c.get('text', '')}" for c in comments]
    prompt = (
        "Post:\n"
        f"Tipo: {post.get('kind')} · Tema: {post.get('theme')}\n"
        f"Legenda: {post.get('caption', '')}\n"
        f"Conteúdo e gabarito: {post.get('content', '')}\n\n"
        "Comentários novos:\n" + "\n".join(lines)
        + "\n\nDevolva uma decisão para cada comentário, com o mesmo comment_id."
    )
    return ask(SYSTEM, prompt, Decisions).decisions
