"""Decide o formato do dia e guarda o histórico para não repetir conteúdo."""

import json
from datetime import date
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "history.json"

# Formatos por dia da semana (0 = segunda). Dia com mais de um formato alterna a cada semana.
# brief = carrossel; stories e reel = roteiro próprio do dia; series = nome do quadro no Reel.
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
        "series": "Lê comigo",
        "stories": (
            "1 'speak' com uma frase curta do texto para ler em voz alta (headline = a frase, body = "
            "pronúncia das partes difíceis); 1 'fill' com uma frase do texto com lacuna ___ e options = "
            "2-3 palavras; 1 'tip'; 1 'answer' com a palavra da lacuna."
        ),
        "reel": (
            "hook ('Consegue ler isso?'); 1 'read' com 2-3 frases curtas do texto (title = o texto, "
            "say_en lê o mesmo texto, say_pt vazio); 2-3 'term' com as palavras difíceis; cta pedindo "
            "para comentar 'consegui'."
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
        "series": "Adivinha pelo emoji",
        "stories": (
            "2 'guess' (emoji de um objeto do post, headline 'Como se diz isso em inglês?', body com a "
            "dica de letras, ex: '_ _ _ _ _ · 5 letras'); 1 'tip'; 1 'answer' com as palavras dos dois."
        ),
        "reel": (
            "hook; 2-3 pares 'question' (emoji do objeto, title 'Como se diz?', say_pt faz a pergunta) → "
            "'reveal' (title = a palavra, text = tradução, say_en = a palavra); cta."
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
        "series": "Expressão do dia",
        "stories": (
            "1 'poll' ('O que significa *X*?' com 2 opções: a tradução literal errada e a certa); 1 "
            "'speak' com a expressão numa frase do dia a dia; 1 'answer'."
        ),
        "reel": (
            "hook; 1 'term' (expressão + significado); 2 'example' em situações diferentes; se houver "
            "tradução literal que brasileiro usa errado, um par 'wrong' → 'right'; cta."
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
        "series": "Não confunda",
        "stories": (
            "1 'truefalse' com uma afirmação sobre um dos pares (ex: 'Pretend significa pretender'); 1 "
            "'poll' com uma frase de lacuna no headline e os dois termos do par como options; 1 'answer' "
            "com as duas respostas."
        ),
        "reel": (
            "hook; 1-2 'versus' (title 'night | knight', text 'noite | cavaleiro', say_en os dois "
            "termos); 'question' com uma frase de lacuna e as duas opções em text; 'reveal'; cta."
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
        "series": "Fala certo",
        "stories": (
            "1 'fix' com um erro clássico diferente dos do post (headline = a frase errada, *asteriscos* "
            "na parte errada) pedindo a correção por DM; 1 'tip'; 1 'answer' com a frase certa."
        ),
        "reel": (
            "hook; 2 pares 'wrong' → 'right'; cta."
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
        "series": "Você sabia?",
        "stories": (
            "1 'truefalse' com uma curiosidade (pode ser verdadeira ou falsa); 1 'guess' (emoji que leva "
            "à palavra do post); 1 'tip'; 1 'answer' com as duas respostas."
        ),
        "reel": (
            "hook com a curiosidade; 'question' ('De onde vem X?' ou 'O que significa X?', alternativas "
            "em text); 'reveal' com a explicação; 1 'example'; cta."
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
        "series": "Situação real",
        "stories": (
            "1 'poll' ('Qual você usaria?' com 2 frases: uma travada/literal e uma natural); 1 'speak' "
            "com uma frase do post para treinar em voz alta; 1 'answer'."
        ),
        "reel": (
            "hook com a situação (ex: 'No restaurante nos EUA'); 3-4 'example' na ordem em que acontecem "
            "(title = a frase, text = tradução, say_en = a frase); cta."
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
        "series": "Quiz relâmpago",
        "stories": (
            "2-3 perguntas sobre termos da semana, misturando 'question' (3 alternativas), 'truefalse' e "
            "'guess'; 1 'answer' com todas as respostas."
        ),
        "reel": (
            "hook ('Acerta as 3?'); 3 pares 'question' → 'reveal' com termos da semana; cta 'quantas você "
            "acertou?'."
        ),
    },
    # Fora do calendário (weekday None): só roda com --format ou, o "milestone", quando uma meta é batida.
    "milestone": {
        "weekday": None,
        "label": "Meta de seguidores",
        "cover": "hero",
        "brief": (
            "Post comemorativo da meta de seguidores (o número e a próxima meta vêm no prompt). Festa e "
            "gratidão, mas ensinando: cover 'hero' com o número no title (ex: '*1.000* obrigados!') e emoji "
            "🎉; 1 'list' com 4-5 expressões em inglês para comemorar e agradecer (ex: We did it!, I couldn't "
            "have done it without you); 1 'list' relembrando os 3-4 conteúdos que mais fizeram sucesso (lista "
            "no prompt, com o termo em inglês e a tradução); 1 'term' com uma palavra de presente; cta pedindo "
            "para compartilhar com um amigo que quer aprender inglês, rumo à próxima meta."
        ),
        "series": "Obrigado!",
        "stories": (
            "1 'tip' agradecendo, com o número; 1 'poll' 'Qual foi seu post favorito?' com 2 dos conteúdos "
            "de sucesso; 1 'question' 'Rumo à próxima meta: o que você quer aprender?' com 3 opções; 1 "
            "'answer' agradecendo e prometendo o conteúdo mais votado."
        ),
        "reel": (
            "hook com o número (ex: 'Somos *1.000*!'); 2-3 'example' com expressões para comemorar e "
            "agradecer em inglês; cta 'Rumo aos X: compartilha com um amigo e segue'."
        ),
    },
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
        "series": "Boas-vindas",
        "stories": (
            "1 'tip' apresentando a página; 1 'question' 'Qual seu nível de inglês?' com 3 opções; 1 "
            "'answer' dizendo que tem conteúdo para todos os níveis."
        ),
        "reel": (
            "hook apresentando a página; 2-3 'term' ou 'example' com o que se aprende aqui; cta."
        ),
    },
}


# Trilhas temáticas: em alguns dias, o tema do post sai de uma trilha (o formato do dia continua o mesmo).
# Revezam em ordem, então todas aparecem a cada ~2 semanas.
TRACK_DAYS = (1, 3, 5)  # terça, quinta e sábado
TRACKS = {
    "viagem": (
        "Viagem aos EUA e Disney: imigração no aeroporto, hotel, parques (filas, Lightning Lane, "
        "personagens, fotos), restaurante e gorjeta, compras e outlets, Uber, emergências. Frases que o "
        "turista brasileiro realmente usa."
    ),
    "visto": (
        "Visto americano: perguntas comuns na entrevista do consulado (What's the purpose of your trip?, "
        "How long will you stay?, Where do you work?) e como entender e responder em inglês, com o "
        "vocabulário da viagem. Só o inglês: a entrevista no Brasil pode ser feita em português; não dê "
        "orientação jurídica nem 'macetes' para aprovar, e as respostas de exemplo são sempre verdadeiras e simples."
    ),
    "entrevista": (
        "Entrevista de emprego em inglês: perguntas clássicas (Tell me about yourself, Why should we hire "
        "you?, What are your weaknesses?), estruturas de resposta, falar de experiência e salário, e os "
        "erros que brasileiro comete (ex: 'I have 5 years of experience in' × 'I worked'). Vale para qualquer área."
    ),
    "trabalho_dev": (
        "Inglês no trabalho para desenvolvedores: daily/standup, code review e PR, Slack, reportar bug, "
        "deploy, estimativas, reuniões com time gringo, phrasal verbs de tech (roll back, ship, figure out, "
        "look into) e os erros comuns de dev brasileiro (ex: 'I will do a PR' × 'I'll open a PR')."
    ),
    "trabalho": (
        "Inglês no trabalho em outras profissões: reuniões e calls, e-mail profissional, atendimento ao "
        "cliente, vendas, saúde, hotelaria; frases para pedir ajuda, discordar com educação e marcar reunião."
    ),
}


def track_for(day: date) -> str:
    """Trilha do dia, ou vazio nos dias sem trilha (e no quiz de domingo, que revisa a semana)."""
    if day.weekday() not in TRACK_DAYS:
        return ""
    n = (day.toordinal() // 7) * len(TRACK_DAYS) + TRACK_DAYS.index(day.weekday())
    return list(TRACKS)[n % len(TRACKS)]


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


def record(day: date, fmt: str, theme: str, terms: list, track: str = "") -> None:
    history = [e for e in load_history() if e["date"] != day.isoformat()]
    entry = {"date": day.isoformat(), "format": fmt, "theme": theme, "terms": terms}
    if track:
        entry["track"] = track
    history.append(entry)
    history.sort(key=lambda e: e["date"])
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
