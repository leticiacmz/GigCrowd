# Relatório — Auditoria e correção do modelo de festivais (GigCrowd)

Fase de auditoria ponta a ponta do modelo de festivais: três níveis (show individual / edição / festival geral), integridade de lineup e relações, e presença por usuário (Vou / Talvez / sem resposta — "Não vou" não existe no produto).

---

## 1. Causas concretas encontradas

**C1 — As duas portas do festival discordavam (bug de serviço).**
`GET /events/{id}/festival` (porta "por data") filtrava edições apenas pelo `festival.series_id` **armazenado** + filtro de proveniência. `GET /festivals/series/{id}` (porta "série") já usava fallback de URL e re-checagem de identidade. Como **442 das 549 edições** nunca tiveram o bloco `festival` gravado (a série só existe na URL Songkick), a porta por data escondia edições: ao vivo, o evento Sudoeste TMN 2010 (`6ad29df321aa1d31471d1a6d`) listava **1** edição enquanto a série `122911` listava **3**.

**C2 — Presença em edição de festival creditava o lineup inteiro (bug de semântica).**
O importador grava o bill resolvido em `artist_slugs` (necessário para a página de cada artista alcançar a data). `personal_artist_slugs`, usado por *artists seen* e pelo histórico por artista, lia essas referências diretas — então confirmar ida a um festival creditava **todos os artistas do bill** à pessoa. Concerto continua creditando o bill direto (multi-ato é um show só).

**C3 — Página geral sem filtro por país.**
A lista de edições mostrava tudo (ex.: Lollapalooza série 1235 = 10 edições em 4 países) sem forma de restringir por país.

**C4 — Id malformado na URL → 500 (descoberto durante a validação).**
`EventRepository.get_by_id` chamava `ObjectId(event_id)` sem validar. Um id truncado (23 caracteres) gerava `InvalidId` → 500 **sem cabeçalhos CORS** — o navegador mostrava erro de CORS e "Evento não encontrado" confuso. (Não era dado corrompido: 2736/2736 eventos têm `_id` ObjectId; o id malformado foi um erro de transcrição **no script de validação**, que acabou revelando o problema real da rota.)

## 2. Modelo de dados: antes vs depois

| Aspecto | Antes | Depois |
|---|---|---|
| Níveis | 3 níveis existiam no código, mas a porta por data divergia da porta por série | 3 níveis consistentes: show individual (Concert), edição (`FestivalInstance`, `_id` próprio), festival geral (série Songkick) |
| Id. de edição | Bloco armazenado **ou** URL — só a porta de série combinava os dois | `_confirmed_editions()` compartilhada: as duas portas usam fallback de URL + re-checagem `festival_identity`; o registro de chegada é sempre mantido |
| Presença | (user, event) `going\|maybe\|went`; mas ida a festival creditava o bill inteiro em *artists seen* | Presença continua (user, event); **festival credita 0 artistas**; concerto credita as referências diretas |
| Filtro de país | inexistente | select na lista de edições quando há ≥2 países distintos (usa `location.country \|\| venue.country`) |
| Id inválido | 500 | 404 (guard `ObjectId.is_valid` → None → 404 da rota) |

Contrato de presença (inalterado, agora sem divergências): `going | maybe | went`; único por (user, event); `went` exige evento passado; sem resposta = ausência de documento; **"Não vou" não existe no produto** (grep em `.py/.ts/.tsx/.json` = 0 ocorrências — não foi inventado).

## 3. Arquivos alterados/criados (desta fase)

**Backend**
- `app/services/festival_service.py` — `get_festival` com `source_url_fallback=True` + `_confirmed_editions()` compartilhada; docstrings (C1).
- `app/domain/festival.py` — `_is_festival_event` → público `is_festival_event`.
- `app/domain/event_artists.py` — `personal_artist_slugs` retorna vazio para festival (C2), docstring explicando a separação membership×presença.
- `app/repositories/event_repository.py` — guarda `ObjectId.is_valid` em `get_by_id` (C4).
- `app/routes/users.py` — docstring de *artists-seen* alinhada ao contrato fixado.
- Testes: `tests/services/test_festival_series.py` (+2), `tests/domain/test_event_artists.py` (+2), `tests/services/test_show_log_isolation.py` (+1: dois usuários no mesmo show), `tests/routes/test_event_id_lookup.py` (novo, 2).

**Frontend**
- `app/lib/festivalEditions.ts` (novo, puro) + `app/lib/festivalEditions.test.ts` (novo, 6 testes) — país com fallback venue, distintos ordenados, "all".
- `components/festival/FestivalDetails.tsx` — select de país (só com ≥2 países), lista filtrada.
- `messages/pt-BR.json`, `en.json`, `es.json` — `allCountries`, `filterByCountry`.

Nenhuma mudança fora do escopo; as alterações não commitadas da fase anterior foram preservadas; **nada foi commitado/pushado**.

## 4. Migração: nenhuma necessária

Auditoria de dados primeiro (2736 eventos, 549 edições, 13211 artistas, 1179 venues, 105 logs):
- 107 edições com série armazenada / 442 só na URL — **0 inconsistências** entre armazenado e URL, **0 duplicatas** de id Songkick; o fallback de leitura cobre as 442 sem reescrever nada;
- lineup: 32372 entradas, 13089 ids distintos, **100% resolvidas** por id Songkick, 0 órfãs/ambíguas (o drift de slug armazenado é mitigado na leitura);
- nenhum reset, nenhuma coleção limpa, nenhum write no catálogo. Os únicos writes foram logs temporários da validação (criados e removidos; contagem final 105 = inicial). Casos ambíguos registrados em vez de inventados: 2010 tem **duas séries Songkick distintas** ("Sudoeste" `3691` e "Sudoeste TMN" `122911`) — mantidas separadas, nunca fundidas por nome.

## 5. Testes executados (resultados reais)

| Verificação | Resultado |
|---|---|
| Backend completo (`python -m pytest -q`) | **1597 passed, 1 skipped** (baseline 1590+1 + 7 testes novos) |
| Frontend (`npm test`, node --test) | **93 passed, 0 failed** |
| `npx tsc --noEmit` | exit 0 |
| `npm run build` | sucesso (BUILD_ID presente; dev parado → `.next` limpo → build → limpo → dev reiniciado em :3000) |
| API ao vivo, dados reais | Sudoeste data-keyed: **3 edições** (antes 1) = série `122911`: 3; Lolla `1235`: 10 edições, 4 países |
| Presença via API (usuário de teste, dados reais) | festival "went" → *artists seen* **0**; contadores +1; irmã intacta; GET persiste; concerto "went" → credita os artistas do concerto; festival→"maybe" mantém *artists seen*; delete → 404 ("sem resposta"); contadores restaurados; 105 logs ao final |

## 6. Checagens de navegador (Edge headless via Playwright, dados reais)

**21 verificações, `ALL CHECKS PASSED`, re-executadas após restart** (screenshots em `%TEMP%\opencode\gc-browser\shots`):
- filtro de país: opções `Todos os países, Argentina, Brazil, Chile, France`; Brazil → 3 linhas, Argentina → 1, todos → 10; Sudoeste (1 país) **não** mostra o controle;
- lineups por edição: 2015 → 131 artistas, 2027 → 1, **sem mistura**;
- edição → página do evento → link de volta `/festivals/series/1235?edition=…` (ida e volta correta);
- porta por data (Sudoeste) lista 3 edições com a edição de chegada marcada (`aria-current`);
- concerto (Turnmills, id real) → **0** links de festival, 0 lineup de festival; h1 próprio ("David Guetta @ Turnmills");
- títulos: edição 2027 h1 = identidade do festival; edição legada sem bloco mostra o título armazenado (que nomeia o festival) + card de festival;
- presença pela UI: **Vou** → reload persiste; **Talvez** → reload persiste; **Talvez** de novo → retirado ("sem resposta", API 404); botões voltam ao estado ocioso.

## 7. Pendências / observações (na entrega original)

> **Todas resolvidas na continuação — ver seção 8.** O texto original de cada item fica abaixo, para preservar o registro.

1. **3 edições 2027** (Lolla AR/CL/Interlagos) têm `lineup` armazenado com 1 artista enquanto `festival.artist_ids` guarda o bill inteiro (`lineup_state=complete`). Lacuna de enriquecimento/dados, não de relações. → **Eram 7 edições, não 3**; causa-raiz, correção de código e reparo dos dados na seção 8.1.
2. Perfis de série com nome em formato de edição — havia teste fixando esse comportamento de propósito. → O teste foi **reescrito de propósito**; o perfil agora abre com o nome da série (seção 8.2).
3. `--reload` do uvicorn não dispara neste ambiente — mudanças de backend exigem restart manual do processo. → Causa-raiz identificada e alternativa de reload testada (seção 8.3).
4. 500 de id malformado (C4) era pré-existente e foi corrigido com guard mínimo + teste.

> Continuação desta fase (investigação da pendência 1 e demais): ver seção 8 abaixo, apensada depois.

---

## 8. Continuação: pendências da seção 7 resolvidas (código + dados, sem commit)

### 8.1 Pendência 1 — lineups parciais: eram **7** edições, não 3

**Causa-raiz (com trilha de evidência).** O `_merge_for_resync` do repositório (`update_event_by_provider`) sobrescrevia o `lineup` armazenado com qualquer `lineup` não vazio que chegasse. Reimportações de artista trazem um lineup parcial — `[artista da página]`, porque a página do artista só nomeia ele mesmo —, e a trilha mostra o dano: um log `Festival lineup extracted: 66 artists` seguido (mais tarde) da sobrescrita por um reimport de 1 nome. Como `lineup_state` já estava `complete`, o enriquecimento não rodava de novo (só forçado): o dano era permanente. O bill completo **sempre esteve** no mesmo documento, em `festival.artist_ids`/`full_name`; e a página ao vivo do Songkick também devolve o bill inteiro (66 no Interlagos) — nada se perdeu na fonte, só no merge.

**Correção no produto.** `EventRepository._without_shrunken_bill` (novo) + leitura de snapshot em `update_event_by_provider`: para **edição de festival**, um resync nunca encolhe `lineup` nem `festival.artists` (incoming igual ou maior continua escrevendo — correções continuam possíveis); concerto mantém a semântica atual. **+5 testes** em `test_event_repository_resync.py`: um nome não encolhe bill; bill maior entra; tamanho igual corrige; bill vazio preenche; concerto ainda corrige para baixo. A re-sobrescrita agora é impossível mesmo reimportando.

**Reparo dos dados.** Script novo `backend/app/scripts/reenrich_short_festival_lineups.py` (dry-run por padrão; `--apply`): candidatas = edição de festival com endereço legível e bill conhecido `max(len(festival.artist_ids), len(artist_slugs)) >= 2` maior que o lineup armazenado; reparo = force-enqueue + `process_batch` (aditivo e idempotente). Rodado: **549 escaneadas → 7 candidatas → 7 reparadas**:

| edição (id) | bill restaurado |
|---|---|
| San Isidro 2027 (`6ad2995921aa1d31471d0b5d`) | 66 |
| O'Higgins 2027 (`6ad2995921aa1d31471d0b5f`) | 71 |
| Interlagos 2027 (`6ad2995921aa1d31471d0b61`) | 66 |
| Simón Bolívar 2027 (`6ad2995921aa1d31471d0b63`) | 67 |
| Zilker / ACL (`6ad2995921aa1d31471d0b67`) | 86 |
| AMF Festival 2026 (`6ad29de521aa1d31471d1471`) | 8 |
| Rock in Rio 2026 (`6ad2c231b19c2767e615d4bc`) | 166 (85 stubs de artista criados) |

Re-execução do dry-run depois do reparo: **0 candidatas** (idempotente). Verificado no banco (lineup/slugs/artist_ids consistentes), na API e no navegador (66 artistas renderizados na página).

**Decisões registradas.** (a) `festival.artists` nesses documentos permanece 1/0 — é grafia legada do payload, sem leitor de exibição (a UI lê `lineup`); alinhar seria cosmético. (b) ~28 documentos da era Demi Lovato (lineup 0/1, estado `None`, sem bill maior em lugar nenhum) ficaram **fora** do reparo — não havia bill para restaurar; eles não estão bloqueados por `complete`, então o enriquecimento regular ainda pode preenchê-los. (c) A ordem do lineup reparado = a entrada armazenada primeiro (Charli), depois a ordem da página menos ela.

### 8.2 Pendência 2 — nome de edição no perfil de série

Os **106/106** nomes de festival armazenados no banco eram formato de edição (103 com " @ venue", 3 só com ano final), e o `identity.name` da série vinha do primeiro bloco armazenado com nome — daí o perfil da série 1235 abrir como "Lollapalooza 2027 @ Hipódromo de San Isidro".

**Resolução** (`_series_name` no serviço + 3 leituras novas no domínio `festival.py`):

1. nome armazenado **não**-formato-de-edição → como está (preserva caixa/acentos da fonte);
2. nome formato de edição → **corte da assinatura da data** (" @ {venue}" e/ou ano final): "Lollapalooza 2027 @ Hipódromo…" → "Lollapalooza"; "AMF Festival 2026" → "AMF Festival" (mantém a caixa que o slug perderia);
3. senão, **segmento de série do endereço** `/festivals/{id}-{slug}`: ex. bloco sem nome → "Edc Las Vegas";
4. últimos recursos: o nome armazenado como está, depois o título (com a recusa já existente de título com cara de artista).

O nível de **edição não mudou**: a página do evento segue "Lollapalooza 2027 @ Autódromo José Carlos Pace (Interlagos)" (verificado no navegador).

Testes: **+14** no domínio (`tests/domain/test_festival_series_name.py`, novo) e **5 de serviço** (4 reescritos de propósito + 1 novo) — incluindo o que fixava o nome de edição no cabeçalho, agora "o nome de edição não encabeça a página da série", e os de "título com cara de artista", que agora comprovam o nome de série lido do endereço ("Lollapalooza", "Primavera") em vez do rótulo genérico. Ao vivo: Lollapalooza, Rock In Rio, AMF Festival, Festival Estereo Picnic, Electric Daisy Carnival, Edc Las Vegas, Réveillon Saudade.

### 8.3 Pendência 3 — `--reload` do uvicorn: causa-raiz fechada + alternativa testada

O reload **detecta** a mudança ("WatchFiles detected changes in 'app\main.py'. Reloading...") mas não recarrega. Causa (mesmo mecanismo nas duas versões presentes — uvicorn 0.52.1 do python do sistema e 0.49.0 do venv — no Windows): o restart manda `CTRL_C_EVENT` ao processo filho e espera o `join()`; num lançamento **sem console interativo** (o caso deste harness) o evento não encerra o filho, o `join()` fica preso e o reloader **nunca mais reage** — uma única linha "Reloading..." em todo o log, filho com o mesmo PID, servindo o código antigo (o espaço em branco nas linhas seguintes do log é o workaround do próprio uvicorn, `sys.stdout.write(" ")`). Evidência: touch em `app/main.py` na instância velha → nenhuma reação; instância nova → detecta, loga e trava de novo no restart.

No lugar: a instância atual do backend foi **reiniciada manualmente** e roda o código final; e foi testada uma alternativa que funciona neste ambiente — o supervisor do próprio `watchfiles`:

`python -m watchfiles --filter python "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"`

(ele **mata e relança** o processo, sem depender de Ctrl+C; testado na :8001: `1 change detected` → PID novo em ~7 s). Regra prática mantida: mudou backend → reiniciar o processo (ou usar o supervisor).

### 8.4 Validação desta continuação

| Verificação | Resultado |
|---|---|
| Suíte backend completa | **1627 passed, 1 skipped** (+30 vs. 1597: 14 domínio nome-de-série, 10 script de reparo, 5 guarda de resync, 1 serviço; 3 min) |
| Reparo de lineups | 7/7 restauradas; re-dry-run = **0 candidatas** |
| API ao vivo (dados reais) | séries com nome de série: Lollapalooza, Rock In Rio, AMF Festival, Festival Estereo Picnic, Electric Daisy Carnival, Edc Las Vegas, Réveillon Saudade; lineup 66 na série 1235 |
| Navegador (probe novo `series-name-check.cjs`) | **9/9 OK, ALL CHECKS PASSED** — h1 "Lollapalooza" nas duas portas (série e data), lineup 66 renderizado, página de evento mantém o nome de edição (screenshot em `%TEMP%\opencode\gc-browser\shots\series-name-header.png`) |
| Reload | uvicorn `--reload` trava (causa na 8.3); supervisão `watchfiles` testada OK |

Arquivos desta continuação (todos não commitados, junto com o restante): `backend/app/domain/festival.py`, `backend/app/services/festival_service.py`, `backend/app/repositories/event_repository.py`, `backend/app/scripts/reenrich_short_festival_lineups.py` (novo), `backend/tests/domain/test_festival_series_name.py` (novo), `backend/tests/scripts/test_reenrich_short_festival_lineups.py` (novo), `backend/tests/repositories/test_event_repository_resync.py`, `backend/tests/services/test_festival_service.py`, `backend/tests/services/test_import_reports_extraction_gaps.py`. Nenhum commit/push; no banco, apenas o reparo dos 7 documentos.
