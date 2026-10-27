"""Estruturas de dados trocadas entre redator, revisor e renderizador.

Todos os campos são obrigatórios (strings vazias quando não se aplicam) para
manter o schema compatível com structured outputs da Claude API.
"""

from typing import List, Literal

from pydantic import BaseModel, Field, model_validator

Level = Literal["A1", "A2", "B1", "B2", "C1"]
Layout = Literal["auto", "statement", "equation", "versus", "grid", "hero", "dark"]


class Item(BaseModel):
    en: str = Field(description="Termo/frase em inglês")
    pt: str = Field(description="Tradução natural para português do Brasil")
    pronunciation: str = Field(
        description="Pronúncia aportuguesada com sílaba tônica em MAIÚSCULAS, ex: 'pai-NÉ-pol'. Vazio se não fizer sentido."
    )
    example_en: str = Field(description="Frase curta de exemplo em inglês, ou vazio")
    example_pt: str = Field(description="Tradução do exemplo, ou vazio")
    emoji: str = Field(description="Um único emoji que ilustra o item, ou vazio")


class Slide(BaseModel):
    kind: Literal["cover", "term", "reading", "list", "compare", "quiz", "cta"]
    title: str
    subtitle: str
    body: str = Field(description="Texto corrido (usado em 'reading' e 'cta'); vazio nos outros")
    items: List[Item]
    note: str = Field(description="Observação/dica curta no rodapé do slide, ou vazio")
    layout: Layout = Field(description="Só na cover: o desenho da capa. Nos outros slides use 'auto'")
    strike: str = Field(description="Só na cover 'statement': a palavra errada que aparece riscada; senão vazio")

    @model_validator(mode="before")
    @classmethod
    def _old_packs(cls, data):
        # Pacotes gerados antes das capas variadas não têm layout/strike.
        if isinstance(data, dict):
            data.setdefault("layout", "auto")
            data.setdefault("strike", "")
        return data


class Story(BaseModel):
    kind: Literal["question", "answer", "tip", "challenge"]
    headline: str
    body: str
    options: List[str] = Field(description="Alternativas (só em 'question'), senão lista vazia")
    answer: str = Field(description="Resposta correta (em 'question' e 'answer'), senão vazio")


class ContentPack(BaseModel):
    format: str
    theme: str = Field(description="Tema do dia em poucas palavras")
    level: Level
    feed: List[Slide] = Field(description="Carrossel de 4 a 8 slides; o primeiro é 'cover', o último é 'cta'")
    caption: str = Field(description="Legenda do post em PT-BR, com gancho, conteúdo extra e pergunta para comentários")
    hashtags: List[str] = Field(description="8 a 15 hashtags sem o símbolo #")
    stories: List[Story] = Field(description="3 a 5 stories do dia")
    terms_used: List[str] = Field(description="Termos/expressões em inglês ensinados hoje, em minúsculas")


class Issue(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    location: str = Field(description="Onde está o problema, ex: 'feed[2].items[1].pronunciation'")
    problem: str
    fix: str


class Review(BaseModel):
    approved: bool = Field(description="true só se não houver issues 'blocker' nem 'major'")
    issues: List[Issue]
    summary: str
