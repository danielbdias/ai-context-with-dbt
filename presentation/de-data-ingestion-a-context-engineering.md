---
marp: true
title: "De data ingestion a context engineering"
description: "Construindo contextos de agentes de IA confiáveis com dbt"
author: Daniel Dias
paginate: true
---

# De data ingestion a context engineering

Construindo contextos de agentes de IA confiáveis com dbt

---

# Daniel Dias

**Senior Software Engineer, dbt Labs**

Doutorando em IA na USP, apaixonado por criar Dev Tools

- LinkedIn: [@danielbdias](https://linkedin.com/in/danielbdias)
- Github: [@danielbdias](https://github.com/danielbdias)

<!-- Foto: Daniel-2026.JPG -->

---

# Um desafio: mudanças de dados em um hospital

Temos um processo de ETL que extrai e transmite dados para o Data Lake do
hospital. Isso permite que os analistas gerem relatórios estratégicos.
**O processo funciona perfeitamente!**

```
Fontes                                  Pipeline ETL
──────────────────────────────────      ─────────────────────────────────────
Cadastro de pacientes               ┐
Dados contábeis entre planos de     │
  saúde e hospital                  ├──▶ Extract ──▶ Transform ──▶ Load ──▶ Data Warehouse
Bancos locais com exames            │
…                                   ┘
```

---

# Um desafio: mudanças de dados em um hospital

Recentemente, um órgão regulador solicitou dados adicionais para relatórios,
incluindo **Informações de Identificação Pessoal (PII)** rastreáveis.

```
Fontes                                  Pipeline ETL
──────────────────────────────────      ─────────────────────────────────────
Cadastro de pacientes               ┐
Dados contábeis entre planos de     │
  saúde e hospital                  ├──▶ Extract ──▶ Transform ──▶ Load ──▶ Data Warehouse
Bancos locais com exames            │                    ⚠️
…                                   ┘
```

---

# Reação dos engenheiros de dados a notícia

<!-- GIF: um hamster em pé sobre um trampolim — "duhn duhn duhhnn !!!" -->

---

# Pontos de tensão no ETL

Como a transformação pode ser feito direto com a extração, precisamos criar
outras rotinas de transformação só para os dados novos, passar dias ou semanas
rodando a tarefa.

```
Fontes                                  Pipeline ETL
──────────────────────────────────      ─────────────────────────────────────
Cadastro de pacientes               ┐
Dados contábeis entre planos de     │
  saúde e hospital                  ├──▶ Extract ──▶ Transform ──▶ Load ──▶ Data Warehouse
Bancos locais com exames            │       ▲────────────▲
…                                   ┘       acoplados: retrabalho
```

---

# Nova reação dos engenheiros de dados a notícia

<!-- GIF: um homem de terno e gravata — "no ! god ! please ! no ." -->

---

# Pensando em ETL

```
Fontes                                  Pipeline ETL
──────────────────────────────────      ─────────────────────────────────────
Cadastro de pacientes               ┐
Dados contábeis entre planos de     │
  saúde e hospital                  ├──▶ Extract ──▶ Transform ──▶ Load ──▶ Data Warehouse
Bancos locais com exames            │
…                                   ┘
```

O ETL é um processo otimizado para carregar e estruturar dados antes de chegar
ao data warehouse.

Porém, pode ter pouca flexibilidade em alguns cenários, gerando mais trabalho
para a equipe de dados.

---

# E se mudarmos o paradigma desse processo?

---

# Entra em cena o ELT !

<!-- Imagem: comparação ETL × ELT -->

Fonte: <https://www.dio.me/articles/a-importancia-do-elt-e-etl-no-processo-de-engenharia-de-dados>

---

# Pensando em um novo workflow para o problema

```
Fontes                                  Pipeline ELT
──────────────────────────────────      ─────────────────────────────────────
Cadastro de pacientes               ┐
Dados contábeis entre planos de     │
  saúde e hospital                  ├──▶ Extract & Load ──▶ Data warehouse ──▶ Transform
Bancos locais com exames            │                            ▲────────────────┘
…                                   ┘                       transformação dentro do warehouse
```

---

# Como o ELT pode te ajudar?

- Transformação de dados flexível
- Custos e tempo de processamento reduzidos
- Auditoria e governança de dados facilitadas
- Melhor escalabilidade e desempenho

---

# Perfeito… Mas o que é o dbt? E como ele se encaixa nesse contexto?

---

# O que é o dbt?

O **dbt (data build tool)** é uma ferramenta open-source, que permite a
transformação de dados com boas práticas de engenharia de software.

Atualmente, ela está disponível em duas versões:

- **dbt Core**, sob a licença Apache 2.0: <https://github.com/dbt-labs/dbt-core>
- **dbt Fusion**, sob a licença Elastic License 2.0: <https://github.com/dbt-labs/dbt-fusion>

---

# Como o dbt interage com ecosistema de dados

<!-- Imagem: diagrama do dbt dentro do ecossistema de dados -->

---

# Como a transformação é feita?

A transformação no dbt é estruturada através de um projeto com códigos fonte em
SQL, Yaml e Python.

<!-- Imagem: estrutura de um projeto dbt -->

---

# Como a transformação é feita?

A transformação no dbt é estruturada através de um projeto com códigos fonte em
SQL, Yaml e Python.

As tabelas que foram carregadas no processo de Extract & Load são definidas como
**sources**.

<!-- Imagem: estrutura de um projeto dbt, destacando sources -->

---

# Como a transformação é feita?

A transformação no dbt é estruturada através de um projeto com códigos fonte em
SQL, Yaml e Python.

As tabelas que foram carregadas no processo de Extract & Load são definidas como
**sources**.

As sources começam a ser expostas em **modelos**, escritos como *selects em SQL*.

<!-- Imagem: estrutura de um projeto dbt, destacando models -->

---

# Como a transformação é feita?

A transformação no dbt é estruturada através de um projeto com códigos fonte em
SQL, Yaml e Python.

As tabelas que foram carregadas no processo de Extract & Load são definidas como
**sources**.

As sources começam a ser expostas em **modelos**, escritos como *selects em SQL*.

Com esses modelos podemos começar a estruturar as **regras de negócios** da
transformação e alterá-las facilmente se necessário.

<!-- Imagem: estrutura de um projeto dbt, destacando regras de negócio -->

---

# Melhores práticas de Engenharia de Software

O código do seu projeto dbt pode ser armazenado em um repositório como o Github.

<!-- Imagem: projeto dbt versionado em repositório -->

---

# Melhores práticas de Engenharia de Software

O código do seu projeto dbt pode ser armazenado em um repositório como o Github.

O projeto pode ser **testado** para garantir que seus dados sejam implantados em
produção com segurança.

<!-- Imagem: projeto dbt com testes e deploy -->

---

# ELT executado via dbt

<!-- Imagem: pipeline ELT completo executado com dbt -->

> Nota do apresentador: como estruturar as boas práticas de engenharia de dados.

---

# Video: VS Code extension na prática

<!-- Vídeo: dss_demo.mp4 -->
<https://docs.google.com/file/d/1epTtQuboMH4sRF48lsQetuNLxI4JRcAo/preview>

---

# Video: dbt Platform na prática

<!-- Vídeo: dss_demo_2.mp4 -->
<https://docs.google.com/file/d/1V5hkdLcmcbHM4WjbWEFF71b-UYCB8qHL/preview>

---

# Para saber mais

- Visual Studio Code extension: <https://marketplace.visualstudio.com/items?itemName=dbtLabsInc.dbt>
- dbt Core: <https://github.com/dbt-labs/dbt-core>
- dbt Fusion: <https://github.com/dbt-labs/dbt-fusion>
- Documentação: <https://docs.getdbt.com/>

---

# Obrigado!

getdbt.com

@danielbdias

<!-- QR codes: qrcode_dbt.png, qrcode.png -->

---

# Workshop

**Data Science Summit 2025**

<workshops.us1.dbt.com/workshop>

Senha: `DataScienceSummit2025`

<!-- QR code do workshop -->
