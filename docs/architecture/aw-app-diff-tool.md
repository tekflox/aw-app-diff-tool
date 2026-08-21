---
repo: architecture
path: docs/architecture/aw-app-diff-tool.md
source: generated
edited: false
checksum: sha256:39b4de92ee93e4325bd61dabb4ceb1f0da5406d604be208fc1368a4de639454b
---
# Diff Tool

- **repo**: aw-app-diff-tool
- **layer**: app
- **technologies**: python, react
- **health** (derived): planned

Interactive git diff viewer + commit panel, decoupled from the monolith. Two entry points: an agent's show_diff MCP tool call, or the git repo nav's expand arrow. Multi-file tabs, unified/split view, GitHub-style collapsible context, inline word-diff highlighting, and an embedded Commit & Push panel.

## Connections
- `http` → **aw-workspace** — routes mounted at /api/apps/diff-tool
- `stdio-mcp` → **mcp-gateway** — MCP surface aggregated by the gateway

## MCP tools
- `show_diff`

## Requirements
### Um id vindo da rede vira caminho só depois de provar que é um token simples
- Given os ids são gerados por uuid4().hex internamente, mas o POST /diffs também aceita um diff_id escolhido por quem chama
- When o id é convertido em caminho (repos/aw-app-diff-tool/diff_app/storage.py::_path:111)
- Then qualquer coisa que não seja alfanumérico com hífen ou underscore devolve None e nada é lido nem escrito — a checagem precisa existir mesmo com ids gerados internamente porque o outro caminho de entrada não é gerado internamente, e um id como ../../secrets viraria escrita fora do diretório de dados. Devolver None em vez de levantar mantém a regra: o cache é best-effort e nunca derruba um diff que alguém está esperando
- intended_status: `not_implemented` · derived health: `not_implemented`
- tests: `repos/aw-app-diff-tool/tests/test_storage_persistence.py` (passing)

### Gravação é escreve-e-renomeia, para ninguém ler um arquivo pela metade
- Given o HTML de um diff é grande o bastante para que uma escrita parcial seja observável por um leitor concorrente
- When a entrada é persistida (repos/aw-app-diff-tool/diff_app/storage.py::_write:119, escrevendo em .json.tmp e usando replace:129)
- Then o arquivo final aparece já completo, porque o replace é atômico no mesmo filesystem, e um OSError vira warning em vez de exceção — disco cheio ou montagem somente-leitura devem rebaixar o app ao comportamento antigo, só em memória, e nunca fazer falhar o diff que alguém pediu. Sem o rename, um leitor concorrente pegaria JSON truncado, que é o mesmo sintoma de arquivo corrompido mas sem causa persistente
- intended_status: `not_implemented` · derived health: `not_implemented`
- tests: `repos/aw-app-diff-tool/tests/test_storage_persistence.py` (passing)

### Arquivo corrompido é descartado na leitura, não propagado como erro
- Given um arquivo de diff em disco ilegível, truncado, ou cujo conteúdo não corresponde ao id pedido
- When a leitura acontece (repos/aw-app-diff-tool/diff_app/storage.py::_read:134)
- Then o arquivo é apagado, um warning é registrado e o retorno é None, tratado como cache miss comum — e a entrada só é aceita se for dict E o id de dentro bater com o pedido (storage.py:147), o que rejeita um arquivo renomeado à mão para outro nome. Auto-limpar é o que impede um único arquivo ruim de falhar o mesmo id para sempre, já que nada mais nesse fluxo o removeria
- intended_status: `not_implemented` · derived health: `not_implemented`
- tests: `repos/aw-app-diff-tool/tests/test_storage_persistence.py` (passing)

### O diff sobrevive a perder o processo inteiro, e o disco tem teto
- Given um LRU de 50 entradas em memória na frente de um cache em disco write-through, e um container que pode ser recriado a qualquer momento
- When a busca não acha na memória e cai para o disco (repos/aw-app-diff-tool/diff_app/storage.py::get:88-93) e a poda roda a cada escrita (_prune:149)
- Then um diff criado antes do restart continua abrindo, ausência na memória é tratada como despejo do LRU ou perda de restart e não como inexistência, e os arquivos mais antigos por mtime são removidos acima do teto — sem o teto um app que gera HTML grande enche o disco do workspace devagar, e o sintoma aparece em outro app qualquer, que é o modo de falha mais caro que esta casa tem
- intended_status: `not_implemented` · derived health: `not_implemented`
- tests: `repos/aw-app-diff-tool/tests/test_storage_persistence.py` (passing)

### O diretório de dados segue a convenção do workspace e não cai no home
- Given o app precisa de um lugar durável que sobreviva a reinstalação, e AW_WORKSPACE_HOME pode não estar no ambiente
- When o diretório padrão é resolvido (repos/aw-app-diff-tool/diff_app/storage.py::default_data_dir:47)
- Then o caminho é &lt;AW_WORKSPACE_HOME&gt;/data/diff-tool, o mesmo layout que todo outro app usa, e sem a variável o fallback é o diretório do container e NÃO o home do usuário (storage.py:56) — cair no home produziria um caminho que existe, é gravável e parece funcionar, enquanto some a cada recriação de container. Sem data_dir nenhum o app volta ao comportamento antigo, só memória, o que mantém o modo standalone viável
- intended_status: `not_implemented` · derived health: `not_implemented`
- tests: `repos/aw-app-diff-tool/tests/test_storage_persistence.py` (passing)
