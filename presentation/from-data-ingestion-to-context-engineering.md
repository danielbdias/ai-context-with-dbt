---
marp: true
title: "From data ingestion to context engineering"
description: "Building reliable AI agent contexts with dbt"
author: Daniel Dias
paginate: true
style: |
  section.split {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto 1fr;
    column-gap: 2rem;
    align-content: start;
  }
  section.split h1 {
    grid-column: 1 / -1;
  }
  section.split figure,
  section.split p:has(> img:only-child) {
    margin: 0;
    align-self: center;
  }
  section.split img {
    width: 100%;
    max-height: 440px;
    object-fit: contain;
  }
  section.diagram {
    display: flex;
    flex-direction: column;
  }
  section.diagram .mermaid {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-top: 0.5rem;
  }
  section.diagram .mermaid svg {
    height: 100%;
    width: auto;
    max-width: 100%;
  }
  section.media {
    display: flex;
    flex-direction: column;
  }
  section.media p:has(> img:only-child),
  section.media .media-frame {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
  }
  /* PDF cannot animate a GIF, so the print build swaps in a still frame. */
  .only-print {
    display: none;
  }
  @media print {
    .only-screen {
      display: none;
    }
    .only-print {
      display: block;
    }
  }
  section.media img {
    height: 100%;
    width: auto;
    max-width: 100%;
    object-fit: contain;
  }
---

<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";
  mermaid.initialize({
    startOnLoad: true,
    theme: "neutral",
    fontFamily: "Helvetica, Arial, sans-serif",
    // Marp's PDF export drops glyphs from Mermaid's HTML (foreignObject)
    // labels, so render every label as plain SVG text instead. Node labels
    // read the top-level flag; subgraph titles read the flowchart one.
    htmlLabels: false,
    flowchart: {
      htmlLabels: false,
      useMaxWidth: false,
      nodeSpacing: 22,
      rankSpacing: 55,
      wrappingWidth: 280,
    },
  });
</script>

# From data ingestion to context engineering

Building reliable AI agent contexts with dbt

---

<!-- _class: split -->

# Daniel Dias

![Daniel Dias photo](./images/daniel-2026.jpg)

<div>

**Senior Software Engineer, Fivetran + dbt Labs**

PhD candidate in AI at USP, passionate about building dev tools

- LinkedIn: [@danielbdias](https://linkedin.com/in/danielbdias)
- Github: [@danielbdias](https://github.com/danielbdias)

</div>

---

<!-- _class: diagram -->

# A challenge: data changes at a hospital

We have an ETL process that extracts and streams data into the hospital's data
lake. That lets the analysts produce strategic reports.
**The process works perfectly!**

<div class="mermaid">
flowchart LR
  subgraph sources["Sources"]
    direction TB
    records["Patient records"]
    accounting["Accounting data between<br/>health plans and the hospital"]
    exams["Local databases with<br/>exam results"]
    more["…"]
  end
  subgraph etl["ETL pipeline"]
    direction LR
    extract["Extract"] --> transform["Transform"] --> load["Load"]
  end
  records --> extract
  accounting --> extract
  exams --> extract
  more --> extract
  load --> warehouse[("Data Warehouse")]
</div>

---

# A challenge: data changes at a hospital

A regulator recently asked for additional data in those reports, including
traceable **Personally Identifiable Information (PII)**.

<div class="mermaid">
flowchart LR
  subgraph sources["Sources"]
    direction TB
    records["Patient records"]
    accounting["Accounting data between<br/>health plans and the hospital"]
    exams["Local databases with<br/>exam results"]
    more["…"]
  end
  subgraph etl["ETL pipeline"]
    direction LR
    extract["Extract"] --> transform["Transform ⚠️"] --> load["Load"]
  end
  records --> extract
  accounting --> extract
  exams --> extract
  more --> extract
  load --> warehouse[("Data Warehouse")]
</div>

---

<!-- _class: media -->

# The data engineers' reaction to the news

<div class="media-frame">
  <img class="only-screen" src="./images/dramatic-chipmunk.gif"
       alt="A chipmunk turns to the camera as the music stings" />
  <img class="only-print" src="./images/dramatic-chipmunk-still.png"
       alt="A chipmunk turns to the camera as the music stings" />
</div>

---

# Friction points in ETL

Because the transformation is coupled to the extraction, we have to build
separate transformation routines just for the new data, and spend days or weeks
running the job.

<div class="mermaid">
flowchart LR
  subgraph sources["Sources"]
    direction TB
    records["Patient records"]
    accounting["Accounting data between<br/>health plans and the hospital"]
    exams["Local databases with<br/>exam results"]
    more["…"]
  end
  subgraph etl["ETL pipeline"]
    direction LR
    extract["Extract"] --> transform["Transform ⚠️"] --> load["Load"]
  end
  records --> extract
  accounting --> extract
  exams --> extract
  more --> extract
  load --> warehouse[("Data Warehouse")]
  extract -- coupled: rework --> transform
</div>

---

<!-- _class: media -->

# The data engineers' reaction, take two

<div class="media-frame">
  <img class="only-screen" src="./images/god-please-no.gif"
       alt="A man in a suit recoils in horror, captioned 'NO GOD PLEASE NO! NOOO! NOOO!'" />
  <img class="only-print" src="./images/god-please-no-still.png"
       alt="A man in a suit recoils in horror, captioned 'NO GOD PLEASE NO! NOOO! NOOO!'" />
</div>

---

# Thinking about ETL

- ETL is a process optimized for loading and structuring data before it reaches
the data warehouse.

- But it can be inflexible in some scenarios, creating more work for the data
team.

<div class="mermaid">
flowchart LR
  subgraph sources["Sources"]
    direction TB
    records["Patient records"]
    accounting["Accounting data between<br/>health plans and the hospital"]
    exams["Local databases with<br/>exam results"]
    more["…"]
  end
  subgraph etl["ETL pipeline"]
    direction LR
    extract["Extract"] --> transform["Transform"] --> load["Load"]
  end
  records --> extract
  accounting --> extract
  exams --> extract
  more --> extract
  load --> warehouse[("Data Warehouse")]
</div>

---

# What if we flipped the paradigm?

---

# Enter ELT!

![](./images/etl-vs-elt.png)

Source: <https://www.dio.me/articles/a-importancia-do-elt-e-etl-no-processo-de-engenharia-de-dados>

---

<!-- _class: diagram -->

# A new workflow for the problem

<div class="mermaid">
flowchart LR
  subgraph sources["Sources"]
    direction TB
    records["Patient records"]
    accounting["Accounting data between<br/>health plans and the hospital"]
    exams["Local databases with<br/>exam results"]
    more["…"]
  end
  subgraph elt["ELT pipeline"]
    direction LR
    extract["Extract and Load"] --> warehouse[("Data warehouse")]
    warehouse --> transform["Transform"]
    transform --> warehouse
  end
  records --> extract
  accounting --> extract
  exams --> extract
  more --> extract
</div>

The transformation now runs **inside the warehouse**.

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

Recently it moved to **dbt v2**, under the Apache 2.0 license: <https://github.com/dbt-labs/dbt>

---

# How dbt interacts with the data ecosystem

![](./images/dbt-in-data-space.png)

---

# How is the transformation done?

Transformation in dbt is structured as a project with source code in SQL, YAML
and Python.

<!-- Image: dbt project structure -->
![](./images/dbt-project-structure.png)

---

# How is the transformation done?

Transformation in dbt is structured as a project with source code in SQL, YAML
and Python.

The tables loaded by the Extract & Load step are declared as **sources**.

![](./images/dbt-sources.png)

---

# How is the transformation done?

Transformation in dbt is structured as a project with source code in SQL, YAML
and Python.

The tables loaded by the Extract & Load step are declared as **sources**.

Sources are then exposed through **models**, written as *SQL selects*.

![](./images/dbt-models.png)

---

# How is the transformation done?

Transformation in dbt is structured as a project with source code in SQL, YAML
and Python.

The tables loaded by the Extract & Load step are declared as **sources**.

Sources are then exposed through **models**, written as *SQL selects*.

With those models we can structure the **business rules** of the transformation
and change them easily when needed.

![](./images/dbt-business-rules.png)

---

# Software engineering best practices

Your dbt project code can live in a repository like GitHub.

![](./images/dbt-git-project.png)

---

# Software engineering best practices

Your dbt project code can live in a repository like GitHub.

The project can be **tested** so your data ships to production safely.

![](./images/dbt-tests.png)

---

# ELT run with dbt

![](./images/elt-via-dbt.png)

---

<!-- _class: diagram -->

# Coding time

The example repo: <https://github.com/danielbdias/ai-context-with-dbt>

<div class="mermaid">
flowchart LR
  form["Form<br/>apps/web"] --> pg[("Postgres")]
  pg --> dlt["dlt<br/>apps/el"]
  dlt --> raw[("ClickHouse raw")]
  raw --> dbt["dbt<br/>transform/dbt"]
  dbt --> marts[("marts")]
  marts --> charts["dbt Charts<br/>Superset"]
  marts --> mcp["dbt MCP<br/>Claude"]
</div>

Everything runs through `task` (`task --list`).

<!--
Pre-run before the talk (Docker, about 6 GB RAM): task setup, up, seed, el,
dbt:build, dashboard, mcp:build.
-->

---

# Coding time: sources and models

- **Source**: `transform/dbt/models/staging/_sources.yml` declares
  `raw.submissions`, with freshness (warn after 24h) and descriptions.
- **Model**: `stg_app__submissions.sql` deduplicates with `argMax` and maps
  browsers and OSes through seeds, with `Other` as the fallback.

<!--
Live: task app:open, submit a message (password dssbr, demo only), then
task el && task dbt:build. Optional: task dbt:docs for lineage on :8081.
-->

---

# Coding time: business rules and tests

- **Change a rule**: edit `seeds/browser_family_map.csv`, run
  `task dbt:build`, and the charts change. No pipeline rework.
- **Enforce a rule**: the `normalize_token` macro and the `no_stopwords`
  generic test keep `café` equal to `cafe` and drop stopwords.
- **Git**: it is a repo like any other, with Conventional Commits and PRs.

<!-- Live: task dashboard, then open /overview/ and /words/. -->

---

# Coding time: dbt as the agent's context

- Every model and column has a **description**, enforced by
  `task dbt:coverage`. Marts state their grain and an example query.
- Claude queries the marts through a read-only **dbt MCP** server.
- Guardrails hold on their own: the `mcp_reader` user can only `SELECT` from
  `marts`, so reading `staging` or `raw` fails.
- PII control lives in the grants and the ingestion design, not in a dbt macro.

<!--
Live: run claude at the repo root and ask "what are the top browsers?". Then
ask it to read staging or raw to show ACCESS_DENIED. Fallback: task mcp:smoke.
-->

---

# Learn more

- Visual Studio Code extension: <https://marketplace.visualstudio.com/items?itemName=dbtLabsInc.dbt>
- dbt v2: <https://github.com/dbt-labs/dbt>
- Documentation: <https://docs.getdbt.com/>
- Example repo: <https://github.com/danielbdias/ai-context-with-dbt>

---

# Thank you!

getdbt.com

@danielbdias

![](./images/qr-code-dbt.png)
![](./images/qr-code-personal.png)
