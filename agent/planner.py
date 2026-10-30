"""Decide o formato do dia e guarda o histórico para não repetir conteúdo."""

import json
from datetime import date
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "history.json"

# Formatos por dia da semana (0 = segunda). Dia com mais de um formato alterna a cada semana.
FORMATS = {
    "reading_challenge": {
        "weekday": 0,
        "label": "Desafio de leitura",
        "cover": "dark",
        "brief": (
            "Post 'Se você conseguir ler esse texto, seu inglês é nível X'. "
            "Slides: cover com o desafio e o nível; 1 slide 'reading' com um texto curto e "
            "cotidiano (60-110 palavras) no nível indicado; 1-2 slides 'term' com 4-6 palavras "
            "difíceis do texto; 1 slide 'reading' com a tradução completa; cta pedindo para "
            "comentar 'consegui' ou a palavra que travou."
        ),
    },
    "visual_vocab": {
        "weekday": 1,
        "label": "Vocabulário visual",
        "cover": "grid",
        "brief": (
            "Grade de vocabulário de um único campo semântico (ex: cozinha, aeroporto, "
            "question words, pronomes indefinidos). Slides 'term' com 4-6 itens cada, todos "
            "com emoji e pronúncia aportuguesada. Termine com um 'quiz' e o cta."
        ),
    },
    "idiom": {
        "weekday": 2,
        "label": "Expressão do dia",
        "cover": "statement ou hero",
        "brief": (
            "Uma expressão idiomática ou phrasal verb muito usado no dia a dia nos EUA. "
            "Slides: cover; 'term' com 1 item (significado, pronúncia, exemplo); 'list' com 3-4 "
            "exemplos em contextos diferentes; 'compare' com o erro comum do brasileiro × o "
            "jeito nativo; cta."
        ),
    },
    "confusing_pairs": {
        "weekday": 3,
        "label": "Não confunda",
        "cover": "versus",
        "brief": (
            "Pares que brasileiros confundem: homófonos (night/knight), falsos cognatos "
            "(pretend/fingir), ou singular/plural irregular (person/people). Use slides 'compare' "
            "(2 itens cada) para 2-3 pares, um 'quiz' e o cta."
        ),
    },
    "wrong_right": {
        "weekday": 3,
        "label": "Fala certo",
        "cover": "fix",
        "brief": (
            "Erros clássicos de brasileiro em frases do dia a dia, no estilo 'não diga × diga' "
            "(ex: 'I have 27 years old' × 'I am 27 years old', 'I lost the bus' × 'I missed the bus'). "
            "A cover já é o primeiro erro (layout 'fix', 2 itens). Depois 4-6 slides 'fix', um erro "
            "por slide, e o cta. Frases curtas e completas; marque com *asteriscos* só a(s) palavra(s) "
            "que muda(m) entre a errada e a certa."
        ),
    },
    "word_curiosity": {
        "weekday": 4,
        "label": "Curiosidade",
        "cover": "equation, versus ou hero",
        "brief": (
            "Curiosidade sobre uma palavra: origem, palavra-valise (hungry + angry = hangry), "
            "gíria nova, diferença EUA × Reino Unido. Slides: cover com gancho curioso; "
            "'compare' ou 'term' explicando; 'list' com 3-4 exemplos de uso; cta."
        ),
    },
    "situation_phrases": {
        "weekday": 5,
        "label": "Frases para situações",
        "cover": "hero ou grid",
        "brief": (
            "Frases prontas para uma situação real (pedir comida, check-in no hotel, small talk "
            "no trabalho, farmácia). Slides 'list' com 4-5 frases cada (en, pt, pronúncia "
            "quando ajudar), até 3 slides de lista, depois cta."
        ),
    },
    "weekly_quiz": {
        "weekday": 6,
        "label": "Quiz da semana",
        "cover": "grid ou hero",
        "brief": (
            "Revisão do que foi ensinado nos últimos 6 dias (veja os termos recentes). "
            "Slides 'quiz' com 1 pergunta e 3 alternativas cada (items = alternativas, a correta "
            "explicada no 'note' do slide seguinte ou no último slide), cta com 'quantas você acertou?'."
        ),
    },
    # Fora do calendário (weekday None): só roda com --format.
    "welcome": {
        "weekday": None,
        "label": "Boas-vindas",
        "cover": "hero",
        "brief": (
            "Post fixado de apresentação da página. Slides: cover acolhedor ('Bem-vindo ao Inglês Leve'); "
            "'list' explicando a proposta (inglês do dia a dia, 1 minuto por dia, pronúncia sem enrolação); "
            "'list' com o que sai em cada dia da semana (seg desafio de leitura, ter vocabulário visual, "
            "qua expressão, qui 'não confunda', sex curiosidade, sáb frases para situações, dom quiz); "
            "um 'term' com a primeira palavra de presente (algo útil e simpático); cta pedindo para seguir "
            "e marcar um amigo que quer aprender inglês. Stories: apresentação e convite para responder "
            "'qual seu nível de inglês?'."
        ),
    },
}


def format_for(day: date) -> str:
    options = [name for name, f in FORMATS.items() if f["weekday"] == day.weekday()]
    return options[day.isocalendar().week % len(options)]


def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def recent_terms(history: list, limit: int = 300) -> list:
    terms = [t for entry in history for t in entry.get("terms", [])]
    return terms[-limit:]


def recent_themes(history: list, limit: int = 30) -> list:
    return [f'{e["date"]} ({e["format"]}): {e["theme"]}' for e in history[-limit:]]


def last_week_terms(history: list, day: date) -> list:
    out = []
    for e in history:
        delta = (day - date.fromisoformat(e["date"])).days
        if 0 < delta <= 6:
            out.extend(e.get("terms", []))
    return out


def record(day: date, fmt: str, theme: str, terms: list) -> None:
    history = [e for e in load_history() if e["date"] != day.isoformat()]
    history.append({"date": day.isoformat(), "format": fmt, "theme": theme, "terms": terms})
    history.sort(key=lambda e: e["date"])
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
