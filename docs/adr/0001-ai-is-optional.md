# ADR-0001: AI is optional

## Status
Accepted

## Context
lesspaper-ngl could have required an LLM for ingest, search, or health.

## Decision
Document management, local OCR/text extraction, Inbox/Process, and PostgreSQL keyword search operate with **no** AI provider. Chat, embeddings, filing suggestions, and summaries run only when configured and privacy allows. `GET /health` does not include AI.

## Rationale
Product principle: “Document management first. AI is an enhancement, not infrastructure.” Enforced in code via optional assignments, `PrivacyGate`, and soft-fail suggestion/summary jobs.

## Consequences
Operators can run a useful DMS offline. Ask and semantic search are unavailable until providers exist. Package metadata still says “AI-native” in places — messaging debt, not behaviour.

## Alternatives considered
AI-mandatory ingest (rejected by implementation). Sidecar-only AI (not used; adapters are in-process HTTP clients).
