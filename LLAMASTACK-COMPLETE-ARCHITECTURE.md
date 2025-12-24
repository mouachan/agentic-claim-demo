# Architecture Complète LlamaStack pour Claims Demo

Basé sur l'audit du cluster existant et la documentation Red Hat OpenShift AI 3.0.

## Sources

- [Red Hat OpenShift AI 3.0 - Working with Llama Stack](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html-single/working_with_llama_stack/working_with_llama_stack)
- [Implement AI safeguards with Python and Llama Stack](https://developers.redhat.com/articles/2025/08/26/implement-ai-safeguards-python-and-llama-stack)
- [Evaluation API - Llama Stack](https://llamastack.github.io/docs/advanced_apis/evaluation)
- [opendatahub-io/llama-stack-demos](https://github.com/opendatahub-io/llama-stack-demos)
- Cluster: LlamaStackDistribution `claims-llamastack` déjà déployée (status: Failed)

## Architecture Complète

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ↓ OpenAI-compatible API (HTTP/REST)
                           │
┌──────────────────────────────────────────────────────────────────────┐
│                   LlamaStack Distribution                             │
│                     (Control Plane)                                   │
│                                                                       │
│  APIs Exposées:                                                      │
│  - /v1/inference          (Chat completions, embeddings)             │
│  - /v1beta/agents         (Agent sessions, turns)                    │
│  - /v1beta/safety         (Guardrails, shields)                      │
│  - /v1beta/eval           (Evaluation tasks)                         │
│  - /v1beta/scoring        (Scoring functions)                        │
│  - /v1beta/tool_runtime   (MCP servers, RAG tools)                   │
│  - /v1beta/vector_io      (Vector DB operations)                     │
│  - /v1beta/datasetio      (Dataset management)                       │
│  - /v1beta/files          (File storage)                             │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    PROVIDERS LAYER                             │ │
│  │                                                                │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │ │
│  │  │  Inference   │  │   Agents     │  │    Safety    │       │ │
│  │  │              │  │              │  │              │       │ │
│  │  │ - sentence-  │  │ - meta-      │  │ - llama-     │       │ │
│  │  │   transformers  │  │   reference │  │   guard      │       │ │
│  │  │ - vllm-inf-1 │  │              │  │ - prompt-    │       │ │
│  │  │ - vllm-inf-2 │  │              │  │   guard      │       │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │ │
│  │                                                                │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │ │
│  │  │ Tool Runtime │  │  Vector IO   │  │   Scoring    │       │ │
│  │  │              │  │              │  │              │       │ │
│  │  │ - rag-       │  │ - milvus     │  │ - basic      │       │ │
│  │  │   runtime    │  │   (inline)   │  │ - llm-as-    │       │ │
│  │  │ - model-     │  │              │  │   judge      │       │ │
│  │  │   context-   │  │              │  │              │       │ │
│  │  │   protocol   │  │              │  │              │       │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │ │
│  │                                                                │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │ │
│  │  │  DatasetIO   │  │    Files     │  │   Eval       │       │ │
│  │  │              │  │              │  │              │       │ │
│  │  │ - huggingface│  │ - localfs    │  │ (to config)  │       │ │
│  │  │              │  │              │  │              │       │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      MODELS LAYER                              │ │
│  │                                                                │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │  LLM Models (via vLLM Inference Providers)              │  │ │
│  │  │                                                          │  │ │
│  │  │  1. llama-instruct-32-3b (provider: vllm-inference-1)   │  │ │
│  │  │     - Model: Llama 3.2 3B Instruct                      │  │ │
│  │  │     - Endpoint: llama-instruct-32-3b-predictor:80/v1    │  │ │
│  │  │     - Features: Tool calling enabled                    │  │ │
│  │  │                                                          │  │ │
│  │  │  2. mistral-3-14b-instruct (provider: vllm-inference-2) │  │ │
│  │  │     - Model: Mistral 3 14B Instruct                     │  │ │
│  │  │     - Endpoint: mistral-3-14b-instruct-predictor:80/v1  │  │ │
│  │  │     - Features: Complex tasks, longer context           │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  │                                                                │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │  Embedding Models (via sentence-transformers)           │  │ │
│  │  │                                                          │  │ │
│  │  │  1. granite-embedding-125m                              │  │ │
│  │  │     - Model: ibm-granite/granite-embedding-125m-english │  │ │
│  │  │     - Dimension: 768                                    │  │ │
│  │  │     - Provider: sentence-transformers (inline)          │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  │                                                                │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │  Safety/Guardrail Models (Shields)                      │  │ │
│  │  │                                                          │  │ │
│  │  │  1. Llama-Guard-3-8B (to configure)                     │  │ │
│  │  │     - Provider: inline::llama-guard                     │  │ │
│  │  │     - Purpose: Filter harmful content (input/output)    │  │ │
│  │  │     - Categories: violence, privacy, hate, etc.         │  │ │
│  │  │                                                          │  │ │
│  │  │  2. Prompt-Guard-86M (to configure)                     │  │ │
│  │  │     - Provider: inline::prompt-guard                    │  │ │
│  │  │     - Purpose: Jailbreak/injection detection            │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
                           │
                           │ MCP Protocol (SSE)
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ↓                  ↓                  ↓
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  OCR MCP     │   │  RAG MCP     │   │ Decision MCP │
│  Server      │   │  Server      │   │  Server      │
│              │   │              │   │              │
│ Tools:       │   │ Tools:       │   │ Tools:       │
│ - ocr_       │   │ - retrieve_  │   │ - make_      │
│   document   │   │   user_info  │   │   final_     │
│              │   │ - retrieve_  │   │   decision   │
│              │   │   similar_   │   │              │
│              │   │   claims     │   │              │
└──────────────┘   └──────────────┘   └──────────────┘
        │                  │                  │
        │                  ↓                  │
        │          ┌──────────────┐           │
        │          │ PostgreSQL + │           │
        │          │   pgvector   │           │
        │          │              │           │
        │          │ - Claims DB  │           │
        │          │ - Contracts  │           │
        │          │ - Embeddings │           │
        └──────────┴──────────────┴───────────┘
```

## Composants Détaillés

### 1. LlamaStack Distribution (Control Plane)

**CRD:** `LlamaStackDistribution` (`llamastack.io/v1alpha1`)

**Rôle:** Orchestrateur central qui:
- Expose les APIs unifiées
- Gère les providers
- Route les requêtes vers les bons services
- Assure la cohérence et la gouvernance

**APIs Disponibles (9):**

| API | Endpoint | Support Level | Description |
|-----|----------|---------------|-------------|
| inference | /v1/inference | GA | Chat completions, embeddings |
| agents | /v1beta/agents | Tech Preview | Agent sessions, turns, tool calling |
| safety | /v1beta/safety | Tech Preview | Input/output filtering, shields |
| eval | /v1beta/eval | Developer Preview | Evaluation tasks |
| scoring | /v1beta/scoring | Tech Preview | Scoring functions, metrics |
| tool_runtime | /v1beta/tool_runtime | Tech Preview | MCP servers, custom tools |
| vector_io | /v1beta/vector_io | Tech Preview | Vector DB operations |
| datasetio | /v1beta/datasetio | Tech Preview | Dataset management |
| files | /v1beta/files | Tech Preview | File storage |

### 2. Providers

#### 2.1 Inference Providers

**a) Sentence Transformers (inline)**
- Provider ID: `sentence-transformers`
- Type: `inline::sentence-transformers`
- Purpose: Embeddings generation
- Model: `granite-embedding-125m`
- Dimension: 768

**b) vLLM Inference 1 (remote)**
- Provider ID: `vllm-inference-1`
- Type: `remote::vllm`
- Model: `llama-instruct-32-3b`
- Endpoint: `http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:80/v1`
- Features: Tool calling enabled

**c) vLLM Inference 2 (remote)**
- Provider ID: `vllm-inference-2`
- Type: `remote::vllm`
- Model: `mistral-3-14b-instruct`
- Endpoint: `http://mistral-3-14b-instruct-predictor.edg-demo.svc.cluster.local:80/v1`
- Use case: Complex tasks, fallback

#### 2.2 Safety Providers

**Option 1: Inline Providers (Llama Guard / Prompt Guard)**

Requires deploying guard models as InferenceServices:

```yaml
providers:
  safety:
    - provider_id: llama-guard
      provider_type: inline::llama-guard
      config:
        model: meta-llama/Llama-Guard-3-8B
        excluded_categories: []  # [] = all categories enabled

    - provider_id: prompt-guard
      provider_type: inline::prompt-guard
      config:
        model: meta-llama/Prompt-Guard-86M
```

**Shields:**

```yaml
shields:
  - shield_id: llama-guard-shield
    provider_id: llama-guard
    shield_type: llama_guard

  - shield_id: prompt-guard-shield
    provider_id: prompt-guard
    shield_type: prompt_guard
```

**Catégories Llama Guard:**
- Violence & Hate
- Sexual Content
- Criminal Planning
- Guns & Illegal Weapons
- Regulated/Controlled Substances
- Self-Harm
- Privacy violations

**Option 2: TrustyAI Guardrails Orchestrator (Remote Provider) - RECOMMENDED**

TrustyAI provides comprehensive guardrails with built-in detectors via the Guardrails Orchestrator:

```yaml
providers:
  safety:
    - provider_id: trustyai-guardrails
      provider_type: remote::trustyai_guardrails
      config:
        url: http://claims-guardrails-orchestrator.claims-demo.svc.cluster.local:8033

        # Pre-inference detectors (input filtering)
        input_detectors:
          - hap              # Hate, Abuse, Profanity
          - jailbreak        # Jailbreak attempt detection
          - pii              # Personally Identifiable Information
          - gibberish        # Nonsensical text
          - regex_language   # Language filtering

        # Post-inference detectors (output filtering)
        output_detectors:
          - hap              # Hate, Abuse, Profanity
          - toxicity         # Toxic content
          - pii              # PII leakage

        # Behavior on detection
        on_detection:
          block: true
          log: true
          return_error: true
```

**Shields:**

```yaml
shields:
  # Input shield (pre-inference)
  - shield_id: trustyai-input-shield
    provider_id: trustyai-guardrails
    shield_type: trustyai_input
    params:
      detectors: [hap, jailbreak, pii, gibberish]

  # Output shield (post-inference)
  - shield_id: trustyai-output-shield
    provider_id: trustyai-guardrails
    shield_type: trustyai_output
    params:
      detectors: [hap, toxicity, pii]
```

**Benefits of TrustyAI Guardrails:**
- Built-in detectors (HAP, PII, jailbreak, toxicity, gibberish)
- Custom detector support (fraud detection for claims)
- Span-aware processing (chunk-based filtering)
- Pre and post-inference filtering
- FMS Guardrails Orchestrator (open source)
- OpenShift AI 3.0 native integration (GuardrailsOrchestrator CRD)
- Garak red teaming support
- No model deployment required (detector-based, not LLM-based)

**Deployment:**
See `TRUSTYAI-GUARDRAILS-GUIDE.md` for complete setup instructions

#### 2.3 Agents Provider

**Provider:** `meta-reference`
- Type: `inline::meta-reference`
- Features:
  - Agent session management
  - Multi-turn conversations
  - Automatic tool calling orchestration
  - Persistence (SQLite)

#### 2.4 Tool Runtime Providers

**a) RAG Runtime (builtin)**
- Provider ID: `rag-runtime`
- Type: `inline::rag-runtime`
- Purpose: Built-in RAG tools
- Tool group: `builtin::rag`

**b) Model Context Protocol (MCP)**
- Provider ID: `model-context-protocol`
- Type: `remote::model-context-protocol`
- Purpose: External MCP servers integration
- Protocol: SSE (Server-Sent Events)

**Configuration MCP servers:**

```yaml
providers:
  tool_runtime:
    - provider_id: model-context-protocol
      provider_type: remote::model-context-protocol
      config:
        mcp_servers:
          - name: ocr-server
            uri: sse://ocr-mcp-server.claims-demo.svc.cluster.local:8080
            tools:
              - ocr_document

          - name: rag-server
            uri: sse://rag-mcp-server.claims-demo.svc.cluster.local:8080
            tools:
              - retrieve_user_info
              - retrieve_similar_claims

          - name: decision-server
            uri: sse://decision-mcp-server.claims-demo.svc.cluster.local:8080
            tools:
              - make_final_decision
```

**Tool groups à enregistrer:**

```yaml
tool_groups:
  - toolgroup_id: builtin::rag
    provider_id: rag-runtime

  - toolgroup_id: mcp::claims-processing
    provider_id: model-context-protocol
    tools:
      - ocr_document
      - retrieve_user_info
      - retrieve_similar_claims
      - make_final_decision
```

#### 2.5 Vector IO Provider

**Provider:** `milvus`
- Type: `inline::milvus`
- Storage: SQLite (inline for demo)
- Dimension: 768 (match embedding model)

**Configuration:**

```yaml
providers:
  vector_io:
    - provider_id: milvus
      provider_type: inline::milvus
      config:
        db_path: /opt/app-root/src/.llama/distributions/rh/milvus.db
        kvstore:
          type: sqlite
          db_path: /opt/app-root/src/.llama/distributions/rh/milvus_registry.db
```

#### 2.6 Scoring Providers (Evaluation)

**a) Basic Scorer**
- Provider ID: `basic`
- Type: `inline::basic`
- Metrics: Exact match, substring match, etc.

**b) LLM-as-Judge**
- Provider ID: `llm-as-judge`
- Type: `inline::llm-as-judge`
- Uses LLM to evaluate outputs
- Customizable criteria

**Configuration scoring functions:**

```yaml
scoring_fns:
  - scoring_fn_id: claims-accuracy
    provider_id: llm-as-judge
    params:
      type: llm_as_judge
      judge_model: llama-instruct-32-3b
      criteria: |
        Evaluate if the claim decision is accurate based on:
        1. User contract coverage
        2. Similar historical claims
        3. Extracted document data
      score_type: 1-5

  - scoring_fn_id: ocr-quality
    provider_id: basic
    params:
      type: string_match
      metrics: [confidence, completeness]
```

#### 2.7 Eval Provider

**Option 1: Inline Provider (meta-reference)**

```yaml
providers:
  eval:
    - provider_id: meta-reference-eval
      provider_type: inline::meta-reference
      config:
        kvstore:
          type: sqlite
          db_path: /opt/app-root/src/.llama/distributions/rh/eval_store.db
```

**Option 2: TrustyAI LMEval (Remote Provider) - RECOMMENDED**

TrustyAI provides a comprehensive LM Evaluation Harness integration as an external provider:

```yaml
providers:
  eval:
    - provider_id: trustyai-lmeval
      provider_type: remote::trustyai_lmeval
      config:
        url: http://trustyai-lmeval.claims-demo.svc.cluster.local:8080
        vllm_url: http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:80/v1/completions
        namespace: claims-demo
        tls_enabled: false
```

**Benefits of TrustyAI LMEval:**
- 60+ standard benchmarks (MMLU, HellaSwag, ARC, TruthfulQA, etc.)
- Custom evaluation task support
- Multiple metrics (accuracy, perplexity, BLEU, ROUGE, F1)
- Built on EleutherAI's LM Evaluation Harness
- External service (doesn't require agents/safety dependencies)

**Deployment:**
See `TRUSTYAI-EVALUATION-GUIDE.md` for complete setup instructions.

**Benchmarks disponibles:**

```yaml
benchmarks:
  - benchmark_id: claims-processing-bench
    dataset_id: claims-test-dataset
    scoring_functions:
      - claims-accuracy
      - ocr-quality
    metadata:
      description: "Evaluate claims processing pipeline"
```

#### 2.8 DatasetIO Provider

**Provider:** `huggingface`
- Type: `remote::huggingface`
- Purpose: Load evaluation datasets from HuggingFace

**Configuration:**

```yaml
datasets:
  - dataset_id: claims-test-dataset
    provider_id: huggingface
    url: huggingface://your-org/claims-eval-dataset
    metadata:
      num_samples: 100
      split: test
```

### 3. Models

#### 3.1 LLM Models

**Llama 3.2 3B Instruct**
```yaml
- provider_id: vllm-inference-1
  model_id: llama-instruct-32-3b
  model_type: llm
  metadata:
    description: "Llama 3.2 3B Instruct with tool calling"
    display_name: llama-instruct-32-3b
    context_length: 8192
    max_tokens: 16384
```

**Mistral 3 14B Instruct**
```yaml
- provider_id: vllm-inference-2
  model_id: mistral-3-14b-instruct
  model_type: llm
  metadata:
    description: "Mistral 3 14B Instruct for complex tasks"
    display_name: mistral-3-14b-instruct
    context_length: 32768
```

#### 3.2 Embedding Model

**Granite Embedding**
```yaml
- provider_id: sentence-transformers
  model_id: granite-embedding-125m
  provider_model_id: ibm-granite/granite-embedding-125m-english
  model_type: embedding
  metadata:
    embedding_dimension: 768
    max_sequence_length: 512
```

#### 3.3 Safety Models

**Llama Guard 3 8B** (à configurer)
```yaml
- provider_id: llama-guard
  model_id: llama-guard-3-8b
  provider_model_id: meta-llama/Llama-Guard-3-8B
  model_type: safety
  metadata:
    description: "Content safety classification"
```

**Prompt Guard 86M** (à configurer)
```yaml
- provider_id: prompt-guard
  model_id: prompt-guard-86m
  provider_model_id: meta-llama/Prompt-Guard-86M
  model_type: safety
  metadata:
    description: "Jailbreak and injection detection"
```

## Configuration Complète run.yaml

Voir le fichier séparé: `openshift/llamastack/complete-run.yaml`

## Workflow de Traitement d'un Claim

```
1. Frontend → POST /v1beta/agents/turn/create
              {
                "agent_config": {
                  "model": "llama-instruct-32-3b",
                  "tools": ["mcp::claims-processing"],
                  "enable_session_persistence": true
                },
                "messages": [{"role": "user", "content": "Process claim 123"}]
              }

2. LlamaStack → Safety Check (Input Shield)
   - Llama Guard: Check harmful content
   - Prompt Guard: Check jailbreak attempts
   ✓ Pass → Continue

3. LlamaStack → Agents API
   - Create agent session
   - LLM decides which tools to call
   - Returns: tool_calls = [
       {"name": "ocr_document", "args": {...}},
       {"name": "retrieve_user_info", "args": {...}},
       ...
     ]

4. LlamaStack → Tool Runtime (MCP)
   - Route to appropriate MCP servers (SSE protocol)
   - Execute tools in sequence/parallel
   - Collect results

5. LlamaStack → LLM with tool results
   - Generate final response
   - decision = make_final_decision(...)

6. LlamaStack → Safety Check (Output Shield)
   - Llama Guard: Filter response
   ✓ Pass → Return

7. LlamaStack → Evaluation (async)
   - Score with scoring_fns
   - Store metrics for monitoring

8. Response → Frontend
   {
     "turn": {...},
     "messages": [...],
     "stop_reason": "end_of_turn"
   }
```

## Monitoring & Observability

### Métriques Disponibles

**Inference:**
- Requests per second
- Latency (p50, p95, p99)
- Token usage
- Model utilization

**Safety:**
- Shield triggers (input/output)
- Categories detected
- False positive rate

**Agents:**
- Session duration
- Tool calls per session
- Success/failure rate

**Evaluation:**
- Scoring function results
- Benchmark performance
- Dataset coverage

### Endpoints de Monitoring

```
GET /health/live
GET /health/ready
GET /metrics (Prometheus format)
```

## Références

- [Red Hat OpenShift AI 3.0 Documentation](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0)
- [Working with Llama Stack](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html-single/working_with_llama_stack/working_with_llama_stack)
- [Implement AI safeguards with Python](https://developers.redhat.com/articles/2025/08/26/implement-ai-safeguards-python-and-llama-stack)
- [Evaluation API - Llama Stack](https://llamastack.github.io/docs/advanced_apis/evaluation)
- [opendatahub-io/llama-stack-demos](https://github.com/opendatahub-io/llama-stack-demos)
