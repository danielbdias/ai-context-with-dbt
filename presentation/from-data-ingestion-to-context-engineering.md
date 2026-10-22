---
marp: true
title: "From data ingestion to context engineering"
description: "Building reliable AI agent contexts with dbt"
author: Daniel Dias
paginate: true
---

# From data ingestion to context engineering

Building reliable AI agent contexts with dbt

---

# Daniel Dias

**Senior Software Engineer, dbt Labs**

PhD candidate in AI at USP, passionate about building dev tools

- LinkedIn: [@danielbdias](https://linkedin.com/in/danielbdias)
- Github: [@danielbdias](https://github.com/danielbdias)

<!-- Photo: Daniel-2026.JPG -->

---

# A challenge: data changes at a hospital

We have an ETL process that extracts and streams data into the hospital's data
lake. That lets the analysts produce strategic reports.
**The process works perfectly!**

```
Sources                                 ETL pipeline
──────────────────────────────────      ─────────────────────────────────────
Patient records                     ┐
Accounting data between health      │
  plans and the hospital            ├──▶ Extract ──▶ Transform ──▶ Load ──▶ Data Warehouse
Local databases with exam results   │
…                                   ┘
```

---

# A challenge: data changes at a hospital

A regulator recently asked for additional data in those reports, including
traceable **Personally Identifiable Information (PII)**.

```
Sources                                 ETL pipeline
──────────────────────────────────      ─────────────────────────────────────
Patient records                     ┐
Accounting data between health      │
  plans and the hospital            ├──▶ Extract ──▶ Transform ──▶ Load ──▶ Data Warehouse
Local databases with exam results   │                ⚠️
…                                   ┘
```

---

# The data engineers' reaction to the news

<!-- GIF: a hamster is standing on its hind legs on a trampoline and says "duhn duhn duhhnn !!!" -->

---

# Friction points in ETL

Because the transformation is coupled to the extraction, we have to build
separate transformation routines just for the new data, and spend days or weeks
running the job.

```
Sources                                 ETL pipeline
──────────────────────────────────      ─────────────────────────────────────
Patient records                     ┐
Accounting data between health      │
  plans and the hospital            ├──▶ Extract ──▶ Transform ──▶ Load ──▶ Data Warehouse
Local databases with exam results   │      ▲─────────────▲
…                                   ┘      coupled: rework
```

---

# The data engineers' reaction, take two

<!-- GIF: a man in a suit and tie is saying "no ! god ! please ! no ." -->

---

# Thinking about ETL

```
Sources                                 ETL pipeline
──────────────────────────────────      ─────────────────────────────────────
Patient records                     ┐
Accounting data between health      │
  plans and the hospital            ├──▶ Extract ──▶ Transform ──▶ Load ──▶ Data Warehouse
Local databases with exam results   │
…                                   ┘
```

ETL is a process optimized for loading and structuring data before it reaches
the data warehouse.

But it can be inflexible in some scenarios, creating more work for the data
team.

---

# What if we flipped the paradigm?

---

# Enter ELT!

<!-- Image: ETL vs. ELT comparison -->

Source: <https://www.dio.me/articles/a-importancia-do-elt-e-etl-no-processo-de-engenharia-de-dados>

---

# A new workflow for the problem

```
Sources                                 ELT pipeline
──────────────────────────────────      ─────────────────────────────────────
Patient records                     ┐
Accounting data between health      │
  plans and the hospital            ├──▶ Extract & Load ──▶ Data warehouse ──▶ Transform
Local databases with exam results   │                            ▲─────────────────┘
…                                   ┘                      transformation in the warehouse
```

---

# How can ELT help you?

- Flexible data transformation
- Lower cost and processing time
- Easier data auditing and governance
- Better scalability and performance

---

# Great… but what is dbt? And how does it fit in?

---

# What is dbt?

**dbt (data build tool)** is an open-source tool that brings software
engineering best practices to data transformation.

It currently comes in two editions:

- **dbt Core**, under the Apache 2.0 license: <https://github.com/dbt-labs/dbt-core>
- **dbt Fusion**, under the Elastic License 2.0: <https://github.com/dbt-labs/dbt-fusion>

---

# How dbt interacts with the data ecosystem

<!-- Image: diagram of dbt within the data ecosystem -->

---

# How is the transformation done?

Transformation in dbt is structured as a project with source code in SQL, YAML
and Python.

<!-- Image: dbt project structure -->

---

# How is the transformation done?

Transformation in dbt is structured as a project with source code in SQL, YAML
and Python.

The tables loaded by the Extract & Load step are declared as **sources**.

<!-- Image: dbt project structure, highlighting sources -->

---

# How is the transformation done?

Transformation in dbt is structured as a project with source code in SQL, YAML
and Python.

The tables loaded by the Extract & Load step are declared as **sources**.

Sources are then exposed through **models**, written as *SQL selects*.

<!-- Image: dbt project structure, highlighting models -->

---

# How is the transformation done?

Transformation in dbt is structured as a project with source code in SQL, YAML
and Python.

The tables loaded by the Extract & Load step are declared as **sources**.

Sources are then exposed through **models**, written as *SQL selects*.

With those models we can structure the **business rules** of the transformation
and change them easily when needed.

<!-- Image: dbt project structure, highlighting business rules -->

---

# Software engineering best practices

Your dbt project code can live in a repository like GitHub.

<!-- Image: dbt project versioned in a repository -->

---

# Software engineering best practices

Your dbt project code can live in a repository like GitHub.

The project can be **tested** so your data ships to production safely.

<!-- Image: dbt project with tests and deploy -->

---

# ELT run with dbt

<!-- Image: full ELT pipeline run with dbt -->

> Speaker note: how to structure data engineering best practices.

---

# Video: the VS Code extension in action

<!-- Video: dss_demo.mp4 -->
<https://docs.google.com/file/d/1epTtQuboMH4sRF48lsQetuNLxI4JRcAo/preview>

---

# Video: dbt Platform in action

<!-- Video: dss_demo_2.mp4 -->
<https://docs.google.com/file/d/1V5hkdLcmcbHM4WjbWEFF71b-UYCB8qHL/preview>

---

# Learn more

- Visual Studio Code extension: <https://marketplace.visualstudio.com/items?itemName=dbtLabsInc.dbt>
- dbt Core: <https://github.com/dbt-labs/dbt-core>
- dbt Fusion: <https://github.com/dbt-labs/dbt-fusion>
- Documentation: <https://docs.getdbt.com/>

---

# Thank you!

getdbt.com

@danielbdias

<!-- QR codes: qrcode_dbt.png, qrcode.png -->

---

# Workshop

**Data Science Summit 2025**

<workshops.us1.dbt.com/workshop>

Password: `DataScienceSummit2025`

<!-- Workshop QR code -->
