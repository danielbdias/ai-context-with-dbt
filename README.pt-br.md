# ai-context-with-dbt

[English](README.md) | **Português (Brasil)**

Uma demo de ELT em Docker que agentes de IA podem consultar, com um Semantic Layer:

app Postgres -> dlt -> Snowflake `RAW` -> dbt v2 `STAGING` e `MARTS` -> dbt
Charts, e um servidor dbt MCP somente leitura para o Claude, que pode rodar
`show` sobre os marts ou pedir métricas ao Semantic Layer da dbt platform.

> **SOMENTE DEMO.** A senha do formulário `dssbr` é insegura de propósito e
> serve apenas para a demo. Não exponha nenhuma porta além do localhost nem
> reutilize o valor. Todas as portas dos containers são vinculadas a
> 127.0.0.1, mas o warehouse (Snowflake) e o Semantic Layer (dbt platform) são
> serviços remotos, então isto não roda mais offline e consome créditos do
> warehouse.

ChatGPT e endpoints MCP públicos estão fora do escopo.

## Pré-requisitos

- [asdf](https://asdf-vm.com/) com as ferramentas de `.tool-versions` (Python,
  uv, task): `asdf install`
- Docker com Compose (Docker Desktop ou similar), cerca de 6 GB de RAM livres
- `openssl` (usado pelo `task setup` para gerar os secrets)
- Uma conta **Snowflake** e um usuário admin que possa usar `ACCOUNTADMIN` (ele
  cria o database, as roles, os usuários e os warehouses)
- Uma conta **dbt platform** (Starter ou superior) para o Semantic Layer. Sem
  ela, todo o resto funciona, e as ferramentas de métricas retornam um erro

## Quickstart

```bash
task setup        # uv sync, cria o .env com secrets aleatórios, builda a imagem do dbt
# edite o .env: SNOWFLAKE_ACCOUNT=orgname-accountname
export SNOWFLAKE_ADMIN_USER=... SNOWFLAKE_ADMIN_PASSWORD=...
task snowflake:setup   # uma vez: database, roles, usuários, warehouses e grants
task up           # Postgres, migrations e o app web, aguarda ficar saudável
task seed         # envia via POST submissions de exemplo, boas e ruins
task seed:history # opcional: cerca de 60 dias de linhas retroativas para as métricas
task el           # dlt: submissions do Postgres -> Snowflake RAW
task dbt:build    # seeds, models e testes (STAGING, MARTS)
task dashboard    # dbt Charts; abre o board overview
```

O Semantic Layer é configurado uma vez na dbt platform: siga
[docs/semantic-layer.md](docs/semantic-layer.md) e depois coloque `DBT_HOST`,
`DBT_HOST_PREFIX`, `DBT_TOKEN` e `DBT_PROD_ENV_ID` no `.env`.

```bash
task mcp:claude   # builda o dbt-mcp e mostra o setup do Claude Code e do Desktop
task mcp:smoke    # sem GUI: tools, top browsers e uma métrica igual a count(*)
task e2e          # suíte end-to-end (projeto próprio, database Snowflake por execução)
```

Depois abra o formulário (`task app:open`), envie algumas mensagens e rode
novamente `task el && task dbt:build`. Para o Claude Code, rode `claude` a
partir da raiz do repositório, aprove o servidor `dbt` e pergunte "quais são os
top browsers?" ou "que parcela das submissions veio de celulares, por mês?".

`task --list` mostra todo o resto. `task down` para a stack e mantém os dados.
`task reset` também apaga o volume do Postgres e os artefatos do dbt em
`transform/dbt/target`. Ele não mexe no Snowflake.

## Portas (somente 127.0.0.1)

| Porta | Serviço | Task |
|---|---|---|
| 8000 | Formulário web | `task up` |
| 5432 | Postgres | `task up` |
| 8090 | dbt Charts (`/overview/`, `/words/`) | `task dashboard` |
| 8081 | dbt docs | `task dbt:docs` |

O projeto e2e usa 15432, 18000, 18090 e 18081. Se outro Postgres já usa a 5432
na sua máquina, defina `POSTGRES_PORT` no `.env` (veja
[docs/debugging.md](docs/debugging.md)).

## Docs

Os documentos abaixo estão em inglês.

- [docs/architecture.md](docs/architecture.md): diagrama, componentes, fluxo de dados
- [docs/semantic-layer.md](docs/semantic-layer.md): configurando a dbt platform
- [docs/pii.md](docs/pii.md): o que é armazenado e onde
- [docs/grants-matrix.md](docs/grants-matrix.md): quem pode ler o quê
- [docs/agent-guide.md](docs/agent-guide.md): como os agentes devem consultar os marts e as métricas
- [mcp/README.md](mcp/README.md): setup do Claude Code e do Desktop
- [dashboard/charts/README.md](dashboard/charts/README.md): os boards do dbt Charts
- [docs/test-strategy.md](docs/test-strategy.md): pirâmide de testes, gates, mapa do e2e
- [docs/debugging.md](docs/debugging.md): debugging por hop e modos de falha conhecidos
- [plan.md](plan.md) e [spec.md](spec.md): o plano e os requisitos originais
  (o design com ClickHouse, substituído pela migração descrita acima)
