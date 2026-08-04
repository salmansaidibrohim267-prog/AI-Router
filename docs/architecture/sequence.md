# Architecture — Sequence Diagrams

Sequence diagrams for the most important request flows. All diagrams are
text/mermaid (no images, renderable in any GitHub markdown viewer).

## 1. Chat completion with failover

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API layer
    participant R as Router
    participant P1 as Provider A (OpenAI)
    participant P2 as Provider B (Anthropic)

    C->>A: POST /v1/chat/completions
    A->>A: auth + tenancy + rate limit + audit
    A->>R: route(model, messages)
    R->>R: score providers (health, priority, cost)
    R->>P1: request
    P1-->>R: failure (or timeout/circuit open)
    R-->>A: fallback to P2
    R->>P2: request
    P2-->>R: 200 OK (or SSE stream)
    R-->>A: normalized response + metrics
    A-->>C: response
```

## 2. RAG retrieval

```mermaid
sequenceDiagram
    participant C as Client
    participant K as Knowledge API
    participant V as Vector store
    participant RR as Reranker
    participant LLM as LLM provider

    C->>K: POST /vector/search {query}
    K->>R: embed (query)
    R->>R: top-K candidates
    R-->>K: candidates
    K->>RR: rerank candidates
    RR-->>K: ordered results
    K-->>C: hits + scores
    Note over C,LLM: Optional grounded completion
    C->>K: POST /v1/chat/completions (with context)
    K->>LLM: completion with retrieved context
    LLM-->>K: answer + citations
    K-->>C: answer
```

## 3. Plugin request hooks

```mermaid
sequenceDiagram
    participant C as Client
    participant P as Poller
    participant Router as Router
    participant L as Listening

    C->>P: request
    P->>Router: pre-request hooks
    Router->>L: provider call
    L-->>Router: response
    Router-->>P: post-request hooks
    P-->>C: response
```

## 4. Distributed task execution

```mermaid
sequenceDiagram
    participant U as Client
    participant W as Worker
    participant Q as Queue (Redis)
    participant S as Scheduler

    U->>W: POST /tasks
    W->>Q: enqueue task
    S->>Q: poll due tasks
    S-->>W: dispatch job (worker)
    W-->>Q: result + status
    W-->>U: /tasks/{id} status
```

## 5. Registration with Plugins in the API layer

```mermaid
sequenceDiagram
    participant C as Client
    participant API as API layer
    participant Secret as Security
    participant Billing as Billing

    C->>API: authenticated request
    API->>API: verify signature/device (security)
    por--Interrupt? no
    API->>Billing: meter usage
    Billing-->>API: quota check
    API-->>C: response
```

## 6. Failure / recovery (circuit breaker)

```mermaid
sequenceDiagram
    participant R as Router
    participant CB as Circuit breaker
    participant P as Provider

    R->>CB: request
    CB->>P: call
    P-->>CB: 5xx
    CB-->>CB: failures++
    Note over CB: threshold → OPEN
    R->>R: skip provider, use fallback
    Note over CB: after cooldown → HALF-OPEN
    CB->>P: probe request
    P-->>CB: success → CLOSED
```