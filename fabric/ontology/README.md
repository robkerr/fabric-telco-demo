# Ontology

[`ontology.yaml`](ontology.yaml) is the shared **business vocabulary** for the solution. It
maps natural-language terms (subscriber, first bill, at-risk, cross-sell candidate, degraded
service) to the underlying tables, columns, and metrics.

## Why it matters

- Gives the **Fabric Data Agent** and **Foundry agents** consistent language so they resolve
  ambiguous questions the same way ("first bill" always means `fact_invoice.is_first_bill = true`).
- Documents entities, synonyms, canonical metrics, and per-journey signals in one place.

## How it's used

1. **Data Agent instructions** — the glossary and entity map inform
   [`../data-agent/config.yaml`](../data-agent/config.yaml) `ai_instructions`.
2. **Foundry agent grounding** — journey agents reference the same terms/signals.
3. **Fabric Ontology item (optional)** — when authoring Fabric's native Ontology item, use this
   file as the specification (entities, relationships, synonyms).

## Structure

| Section | Contents |
|---|---|
| `entities` | Business objects → table, key, synonyms, key attributes, states |
| `metrics` | Canonical metric definitions (aligned to the semantic model measures) |
| `glossary` | Term → precise data-model meaning (disambiguation) |
| `journeys` | Which entities + signals drive each of the three demo journeys |

Keep this file in sync with `../semantic-model/model_spec.yaml` and the Lakehouse gold tables.
