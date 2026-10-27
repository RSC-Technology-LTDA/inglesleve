# insta-english-ai

Agente que gera, todo dia, um carrossel e os stories de uma página de Instagram que ensina inglês
para brasileiros. Ele cuida das etapas **planejar → escrever → revisar → renderizar** e não publica nada:
o pacote do dia fica numa pasta para você aprovar.

```
planner  → escolhe o formato do dia da semana e evita repetir termos (data/history.json)
writer   → Claude gera o pacote (slides, legenda, hashtags, stories) com saída estruturada
reviewer → uma segunda chamada ao Claude, como professor nativo, aponta erros; até 3 rodadas de correção
render   → templates HTML/CSS → PNG via Playwright (feed 1080×1350, stories 1080×1920)
```

## Instalação

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env   # e coloque sua ANTHROPIC_API_KEY
```

## Uso

```bash
.venv/bin/python run_daily.py                       # hoje
.venv/bin/python run_daily.py --date 2026-10-28     # outra data
.venv/bin/python run_daily.py --format idiom        # força um formato
.venv/bin/python run_daily.py --from-json samples/sample_pack.json   # só renderiza, sem API
```

A saída fica em `output/AAAA-MM-DD/`:

| Arquivo | Conteúdo |
|---|---|
| `feed_01.png` … | Slides do carrossel, em ordem |
| `story_01.png` … | Stories (o de tipo "Resposta" é para postar mais tarde) |
| `caption.txt` | Legenda + hashtags, pronta para colar |
| `pack.json` | Conteúdo estruturado (dá para editar e renderizar de novo com `--from-json`) |
| `review.json` | O que o revisor apontou em cada rodada |
| `STATUS` | `approved` ou `needs_human_review` |

Quando o pacote é aprovado mas o revisor aponta ajustes "minor", o redator faz uma rodada de polimento.
A versão polida só substitui a anterior se também for aprovada. Para repolir o pacote de um dia já
gerado, use `--polish` (com `--date`, se não for hoje).

O código de saída é `2` quando o pacote não passa no revisor. Só pacotes aprovados entram no histórico.

## Formatos por dia

| Dia | Formato |
|---|---|
| Seg | Desafio de leitura (texto curto com nível) |
| Ter | Vocabulário visual (grade com emoji e pronúncia) |
| Qua | Expressão do dia |
| Qui | Não confunda (homófonos, falsos cognatos) |
| Sex | Curiosidade de palavra |
| Sáb | Frases para uma situação |
| Dom | Quiz da semana (revisa o que foi ensinado) |

Para editar formatos e instruções, mexa em `agent/planner.py`. O tom e as regras do redator ficam em
`agent/writer.py`, os critérios do revisor em `agent/reviewer.py`, e nome, @ e cores em `brand.json`.

## Publicação automática (GitHub Actions)

O workflow `.github/workflows/daily.yml` roda sozinho em dois horários (horário de Brasília):

| Horário | O que faz |
|---|---|
| **12h** | Gera o pacote do dia com o Claude, converte para JPEG, salva no repositório e publica o carrossel e os stories de pergunta, dica e desafio |
| **18h** | Publica o story de resposta |

- As imagens são servidas pelo `raw.githubusercontent.com`, por isso o **repositório precisa ser público**. A URL é fixada no commit.
- Se o revisor reprovar o pacote, nada é publicado e o job falha. O GitHub te avisa por e-mail. Corrija o `pack.json`, renderize de novo com `--from-json` e rode o workflow à mão.
- O arquivo `output/<data>/published.json` registra o que já foi ao ar. Rodar de novo não duplica posts.
- O cron do GitHub pode atrasar de 5 a 30 minutos em horários de pico.
- Também dá para rodar pela aba **Actions → Publicação diária → Run workflow**, escolhendo horário e data. Marque `dry_run` para só conferir.

### Configuração (uma vez)

**1. App na Meta** (com a conta já como Criador de conteúdo)
1. Em [developers.facebook.com](https://developers.facebook.com/apps), clique em *Criar app* e escolha o caso de uso de gerenciar mensagens e conteúdo no Instagram.
2. Em *Configuração da API com login do Instagram*, vá em *Gerar tokens de acesso* e adicione a conta @inglesleve.br.
3. Autorize as permissões `instagram_business_basic` e `instagram_business_content_publish`.
4. Copie o **token**, que vale 60 dias, e o **ID da conta** que aparece ao lado.

O app pode ficar em modo de desenvolvimento, já que só publica na sua própria conta.

**2. Repositório no GitHub (público)**: em *Settings → Secrets and variables → Actions*, crie:

| Secret | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | Sua chave da Claude API |
| `IG_ACCESS_TOKEN` | Token gerado no passo 1 |
| `IG_USER_ID` | ID da conta do Instagram (opcional; se faltar, o script descobre) |
| `GH_PAT` | Token *fine-grained* do GitHub, só para este repositório, com permissão **Secrets: Read and write**. Usado pela renovação automática do token |

**3. Renovação do token**: `.github/workflows/refresh-token.yml` renova o token do Instagram toda segunda-feira e grava o novo valor no secret.

### Testar localmente

```bash
.venv/bin/python publish.py prepare --date 2026-10-28
.venv/bin/python publish.py noon --date 2026-10-28 --base-url https://raw.githubusercontent.com/<usuario>/<repo>/<sha> --dry-run
```

## Próximos passos

- Ilustrações/mascote com IA de imagem, sempre com o texto vindo do template.
- Usar as métricas do Instagram para ajustar o peso de cada formato.

Fontes: Inter e Bricolage Grotesque (SIL Open Font License, em `assets/fonts`).
