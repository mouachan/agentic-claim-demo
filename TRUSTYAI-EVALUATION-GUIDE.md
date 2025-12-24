# TrustyAI Evaluation Integration with LlamaStack

Date: 2025-12-24
Status: Implementation Guide

## Overview

This guide documents how to integrate **TrustyAI LMEval** as an external evaluation provider for LlamaStack in Red Hat OpenShift AI 3.0. TrustyAI provides comprehensive LLM evaluation capabilities using the LM Evaluation Harness from EleutherAI.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           LlamaStack Distribution (claims-llamastack)        │
│                                                              │
│  APIs:                                                       │
│  - inference                                                 │
│  - eval (via remote provider)                                │
│  - scoring                                                   │
│                                                              │
│  Providers:                                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  eval:                                                  │ │
│  │    - provider_id: trustyai-lmeval                       │ │
│  │      provider_type: remote::trustyai_lmeval             │ │
│  │      config:                                            │ │
│  │        url: http://trustyai-lmeval.claims-demo.svc:8080 │ │
│  │        vllm_url: http://llama-32-3b-predictor:80/v1     │ │
│  │        namespace: claims-demo                           │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ↓ HTTP API calls
┌─────────────────────────────────────────────────────────────┐
│         TrustyAI LMEval Service (External Provider)          │
│                                                              │
│  Deployment: trustyai-lmeval                                 │
│  Image: quay.io/trustyai/lmeval-llama-stack:latest          │
│  Port: 8080                                                  │
│                                                              │
│  Features:                                                   │
│  - LM Evaluation Harness (EleutherAI)                        │
│  - 60+ standard benchmarks                                   │
│  - Custom evaluation tasks                                   │
│  - Multiple metrics (accuracy, perplexity, BLEU, etc.)       │
│                                                              │
│  Environment:                                                │
│  - VLLM_URL: Model inference endpoint                        │
│  - TRUSTYAI_LM_EVAL_NAMESPACE: claims-demo                   │
│  - TRUSTYAI_LMEVAL_TLS: true/false                           │
│  - TRUSTYAI_LMEVAL_CERT_SECRET: tls-secret (if TLS enabled)  │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ↓ Inference requests
┌─────────────────────────────────────────────────────────────┐
│    Llama 3.2 3B InferenceService (vLLM)                      │
│    Endpoint: /v1/completions                                 │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. TrustyAI LMEval Provider

**Repository**: [trustyai-explainability/llama-stack-provider-lmeval](https://github.com/trustyai-explainability/llama-stack-provider-lmeval)
**PyPI Package**: `llama-stack-provider-lmeval`
**Type**: Remote provider (out-of-tree)

The TrustyAI LMEval provider implements the LlamaStack Evaluation API using the LM Evaluation Harness. It runs as a separate service that LlamaStack calls via HTTP.

### 2. LM Evaluation Harness

Open-source framework from EleutherAI for evaluating language models across:
- **60+ standard benchmarks**: MMLU, HellaSwag, ARC, TruthfulQA, etc.
- **Custom tasks**: Define your own evaluation datasets
- **Multiple metrics**: Accuracy, perplexity, BLEU, ROUGE, F1, etc.

### 3. Integration Points

- **LlamaStack Eval API**: `/v1beta/eval/*` endpoints
- **TrustyAI Service**: HTTP service exposing evaluation endpoints
- **Model Inference**: Calls vLLM endpoint for model predictions
- **Results Storage**: Stores evaluation results in LlamaStack

## Deployment

### Step 1: Deploy TrustyAI LMEval Service

Create deployment manifest:

**File**: `openshift/trustyai/lmeval-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trustyai-lmeval
  namespace: claims-demo
  labels:
    app: trustyai-lmeval
    component: evaluation
spec:
  replicas: 1
  selector:
    matchLabels:
      app: trustyai-lmeval
  template:
    metadata:
      labels:
        app: trustyai-lmeval
    spec:
      containers:
      - name: lmeval
        image: quay.io/trustyai/lmeval-llama-stack:latest
        ports:
        - containerPort: 8080
          name: http
          protocol: TCP
        env:
        # Model inference endpoint
        - name: VLLM_URL
          value: "http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:80/v1/completions"

        # Namespace for model deployments
        - name: TRUSTYAI_LM_EVAL_NAMESPACE
          value: "claims-demo"

        # TLS configuration (optional)
        - name: TRUSTYAI_LMEVAL_TLS
          value: "false"  # Set to "true" if using TLS

        # TLS certificate (if TLS enabled)
        # - name: TRUSTYAI_LMEVAL_CERT_SECRET
        #   value: "lmeval-tls-secret"
        # - name: TRUSTYAI_LMEVAL_CERT_FILE
        #   value: "tls.crt"

        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"

        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10

        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: trustyai-lmeval
  namespace: claims-demo
  labels:
    app: trustyai-lmeval
spec:
  selector:
    app: trustyai-lmeval
  ports:
  - name: http
    port: 8080
    targetPort: 8080
    protocol: TCP
  type: ClusterIP
```

Deploy:
```bash
oc apply -f openshift/trustyai/lmeval-deployment.yaml
```

Verify:
```bash
oc get pods -n claims-demo -l app=trustyai-lmeval
oc logs -n claims-demo deployment/trustyai-lmeval
```

### Step 2: Download Provider Configuration

The TrustyAI LMEval provider requires a configuration file to register with LlamaStack.

**Option 1**: Download from GitHub
```bash
curl --create-dirs \
  --output openshift/llamastack/providers.d/remote/eval/trustyai_lmeval.yaml \
  https://raw.githubusercontent.com/trustyai-explainability/llama-stack-provider-lmeval/refs/heads/main/providers.d/remote/eval/trustyai_lmeval.yaml
```

**Option 2**: Create manually

**File**: `openshift/llamastack/providers.d/remote/eval/trustyai_lmeval.yaml`

```yaml
# TrustyAI LMEval provider configuration for LlamaStack
provider_type: remote::trustyai_lmeval

config_schema:
  type: object
  properties:
    url:
      type: string
      description: "URL of the TrustyAI LMEval service"
    vllm_url:
      type: string
      description: "vLLM inference endpoint (v1/completions)"
    namespace:
      type: string
      description: "Kubernetes namespace for model deployments"
    tls_enabled:
      type: boolean
      default: false
      description: "Enable TLS for secure communication"
    cert_secret:
      type: string
      description: "Name of Kubernetes secret containing TLS certificate"
  required:
    - url
    - vllm_url
    - namespace

provider_data_validator: null
```

### Step 3: Configure LlamaStack to Use TrustyAI

Update LlamaStack configuration to add the TrustyAI eval provider.

**File**: `openshift/llamastack/run.yaml` (append to existing config)

```yaml
# Add 'eval' to the apis list
apis:
- agents
- datasetio
- files
- inference
- safety
- eval          # ADD THIS
- scoring
- tool_runtime
- vector_io

# Add eval provider
providers:
  # ... existing providers ...

  eval:
    - provider_id: trustyai-lmeval
      provider_type: remote::trustyai_lmeval
      config:
        url: http://trustyai-lmeval.claims-demo.svc.cluster.local:8080
        vllm_url: http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:80/v1/completions
        namespace: claims-demo
        tls_enabled: false
```

Update ConfigMap:
```bash
oc create configmap llama-stack-config \
  --from-file=run.yaml=openshift/llamastack/run.yaml \
  -n claims-demo \
  --dry-run=client -o yaml | oc replace -f -
```

Restart LlamaStack:
```bash
oc delete pods -l app.kubernetes.io/name=llamastack -n claims-demo
```

Verify provider registered:
```bash
oc exec -n claims-demo deployment/claims-llamastack -- \
  curl -s http://localhost:8321/v1/providers | \
  jq '.data[] | select(.provider_id == "trustyai-lmeval")'
```

Expected output:
```json
{
  "provider_id": "trustyai-lmeval",
  "provider_type": "remote::trustyai_lmeval",
  "config": {
    "url": "http://trustyai-lmeval.claims-demo.svc.cluster.local:8080",
    "vllm_url": "http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:80/v1/completions",
    "namespace": "claims-demo"
  }
}
```

## Usage

### 1. Create Evaluation Task

Create a benchmark evaluation job using the LlamaStack Eval API.

**Example**: Evaluate Llama 3.2 3B on MMLU benchmark

```bash
curl -X POST "http://llamastack.claims-demo.svc.cluster.local:8321/v1beta/eval/job/create" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "claims-llama-mmlu-eval",
    "eval_candidate": {
      "model": "llama-instruct-32-3b",
      "provider_id": "trustyai-lmeval"
    },
    "benchmark_id": "mmlu",
    "num_examples": 100,
    "sampling_params": {
      "temperature": 0.0,
      "top_p": 1.0,
      "max_tokens": 512
    }
  }'
```

Response:
```json
{
  "job_id": "eval-job-12345",
  "status": "running",
  "task_id": "claims-llama-mmlu-eval"
}
```

### 2. Check Evaluation Status

```bash
curl -s "http://llamastack.claims-demo.svc.cluster.local:8321/v1beta/eval/job/12345/status" | jq '.'
```

Response:
```json
{
  "job_id": "eval-job-12345",
  "status": "completed",
  "progress": 100,
  "started_at": "2025-12-24T10:00:00Z",
  "completed_at": "2025-12-24T10:15:00Z"
}
```

### 3. Get Evaluation Results

```bash
curl -s "http://llamastack.claims-demo.svc.cluster.local:8321/v1beta/eval/job/12345/results" | jq '.'
```

Response:
```json
{
  "job_id": "eval-job-12345",
  "benchmark_id": "mmlu",
  "model": "llama-instruct-32-3b",
  "results": {
    "overall_score": 0.68,
    "metrics": {
      "accuracy": 0.68,
      "exact_match": 0.65
    },
    "per_category": {
      "stem": 0.71,
      "humanities": 0.66,
      "social_sciences": 0.69,
      "other": 0.65
    }
  },
  "num_examples": 100,
  "completed_at": "2025-12-24T10:15:00Z"
}
```

## Custom Evaluation for Claims Processing

### Define Custom Evaluation Task

Create a custom evaluation dataset for claims processing accuracy.

**File**: `openshift/trustyai/claims-eval-task.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: claims-eval-dataset
  namespace: claims-demo
data:
  claims_accuracy.json: |
    {
      "task": "claims_accuracy",
      "task_type": "multiple_choice",
      "dataset_name": "custom_claims",
      "description": "Evaluate claim decision accuracy",
      "examples": [
        {
          "input": "User has medical insurance. Claim: Emergency room visit for broken arm. Contract covers: Emergency care with $200 deductible.",
          "target": "approved",
          "choices": ["approved", "denied", "pending"]
        },
        {
          "input": "User has auto insurance. Claim: Routine tire replacement. Contract covers: Collision and comprehensive, excludes maintenance.",
          "target": "denied",
          "choices": ["approved", "denied", "pending"]
        },
        {
          "input": "User has home insurance. Claim: Water damage from burst pipe. Contract covers: Sudden water damage events.",
          "target": "approved",
          "choices": ["approved", "denied", "pending"]
        }
      ],
      "metrics": [
        "accuracy",
        "exact_match"
      ]
    }
```

Deploy dataset:
```bash
oc apply -f openshift/trustyai/claims-eval-task.yaml
```

### Run Custom Evaluation

```bash
curl -X POST "http://llamastack.claims-demo.svc.cluster.local:8321/v1beta/eval/job/create" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "claims-decision-accuracy",
    "eval_candidate": {
      "model": "llama-instruct-32-3b",
      "provider_id": "trustyai-lmeval"
    },
    "benchmark_id": "custom::claims_accuracy",
    "dataset_config": {
      "type": "configmap",
      "name": "claims-eval-dataset",
      "key": "claims_accuracy.json"
    },
    "num_examples": -1,
    "sampling_params": {
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 50
    }
  }'
```

## Available Benchmarks

TrustyAI LMEval supports 60+ standard benchmarks:

### General Knowledge
- **MMLU** (Massive Multitask Language Understanding)
- **ARC** (AI2 Reasoning Challenge)
- **HellaSwag** (Commonsense reasoning)
- **PIQA** (Physical interaction QA)

### Reasoning
- **GPQA** (Graduate-level reasoning)
- **BIG-Bench** (Beyond the Imitation Game)
- **WinoGrande** (Commonsense reasoning)

### Truthfulness
- **TruthfulQA** (Truthfulness evaluation)

### Math & Code
- **GSM8K** (Grade school math)
- **MATH** (High school competition math)
- **HumanEval** (Code generation)

### Safety & Bias
- **BBQ** (Bias benchmark)
- **Toxicity** detection benchmarks

Full list: [EleutherAI LM Evaluation Harness Tasks](https://github.com/EleutherAI/lm-evaluation-harness/tree/main/lm_eval/tasks)

## Metrics

Common evaluation metrics:

- **accuracy**: Proportion of correct predictions
- **exact_match**: Exact string match with target
- **perplexity**: Model confidence (lower is better)
- **BLEU**: Translation quality
- **ROUGE**: Summarization quality
- **F1**: Precision-recall harmonic mean

## Integration with Backend

### Backend Service for Evaluation

**File**: `backend/app/services/evaluation_service.py`

```python
import httpx
from typing import Dict, Any, List
from app.core.config import settings

class EvaluationService:
    """Service for triggering and monitoring LLM evaluations via LlamaStack."""

    def __init__(self):
        self.llamastack_url = settings.llamastack_endpoint
        self.client = httpx.AsyncClient(timeout=600.0)

    async def create_evaluation_job(
        self,
        model: str,
        benchmark_id: str,
        num_examples: int = 100,
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        """Create a new evaluation job."""
        response = await self.client.post(
            f"{self.llamastack_url}/v1beta/eval/job/create",
            json={
                "task_id": f"eval-{model}-{benchmark_id}",
                "eval_candidate": {
                    "model": model,
                    "provider_id": "trustyai-lmeval"
                },
                "benchmark_id": benchmark_id,
                "num_examples": num_examples,
                "sampling_params": {
                    "temperature": temperature,
                    "top_p": 1.0,
                    "max_tokens": 512
                }
            }
        )
        response.raise_for_status()
        return response.json()

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get evaluation job status."""
        response = await self.client.get(
            f"{self.llamastack_url}/v1beta/eval/job/{job_id}/status"
        )
        response.raise_for_status()
        return response.json()

    async def get_job_results(self, job_id: str) -> Dict[str, Any]:
        """Get evaluation job results."""
        response = await self.client.get(
            f"{self.llamastack_url}/v1beta/eval/job/{job_id}/results"
        )
        response.raise_for_status()
        return response.json()

    async def evaluate_claims_model(self) -> Dict[str, Any]:
        """Run custom claims accuracy evaluation."""
        return await self.create_evaluation_job(
            model="llama-instruct-32-3b",
            benchmark_id="custom::claims_accuracy",
            num_examples=-1,  # Use all examples
            temperature=0.1
        )
```

### API Endpoints

**File**: `backend/app/api/evaluation.py`

```python
from fastapi import APIRouter, HTTPException
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/eval", tags=["evaluation"])
eval_service = EvaluationService()

@router.post("/jobs")
async def create_evaluation(
    model: str,
    benchmark: str,
    num_examples: int = 100
):
    """Create a new evaluation job."""
    try:
        result = await eval_service.create_evaluation_job(
            model=model,
            benchmark_id=benchmark,
            num_examples=num_examples
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/{job_id}/status")
async def get_evaluation_status(job_id: str):
    """Get evaluation job status."""
    try:
        return await eval_service.get_job_status(job_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/{job_id}/results")
async def get_evaluation_results(job_id: str):
    """Get evaluation job results."""
    try:
        return await eval_service.get_job_results(job_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/claims-accuracy")
async def evaluate_claims_accuracy():
    """Run claims processing accuracy evaluation."""
    try:
        return await eval_service.evaluate_claims_model()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

Register router in `backend/app/main.py`:
```python
from app.api import evaluation

app.include_router(evaluation.router, prefix="/api/v1")
```

## Troubleshooting

### TrustyAI Service Not Starting

Check logs:
```bash
oc logs -n claims-demo deployment/trustyai-lmeval --tail=100
```

Common issues:
- **Missing VLLM_URL**: Ensure environment variable is set
- **Invalid namespace**: Verify TRUSTYAI_LM_EVAL_NAMESPACE matches deployment namespace
- **Port conflicts**: Check port 8080 is available

### LlamaStack Can't Reach TrustyAI

Verify network connectivity:
```bash
oc exec -n claims-demo deployment/claims-llamastack -- \
  curl -v http://trustyai-lmeval.claims-demo.svc.cluster.local:8080/health
```

Check service:
```bash
oc get svc trustyai-lmeval -n claims-demo
```

### Evaluation Jobs Failing

Check TrustyAI logs:
```bash
oc logs -n claims-demo deployment/trustyai-lmeval -f
```

Verify model endpoint is accessible:
```bash
oc exec -n claims-demo deployment/trustyai-lmeval -- \
  curl -X POST http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:80/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "llama-instruct-32-3b", "prompt": "Test", "max_tokens": 10}'
```

## References

### Official Documentation
- [Red Hat OpenShift AI 3.0 - Evaluating AI Systems](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html/evaluating_ai_systems/evaluating-large-language-models_evaluate)
- [Red Hat OpenShift AI 3.0 - Working with Llama Stack](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html-single/working_with_llama_stack/working_with_llama_stack)
- [Red Hat AI 3 Release Notes](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html-single/release_notes/release_notes)

### TrustyAI Resources
- [TrustyAI LMEval Provider GitHub](https://github.com/trustyai-explainability/llama-stack-provider-lmeval)
- [Getting Started with LMEval Llama Stack External Eval Provider](https://trustyai.org/docs/main/lmeval-lls-tutorial)
- [Running Custom Evaluations with LMEval](https://trustyai.org/docs/main/lmeval-lls-tutorial-custom-data)
- [Getting Started with LM-Eval](https://trustyai.org/docs/main/lm-eval-tutorial)
- [TrustyAI LMEval Provider on PyPI](https://pypi.org/project/llama-stack-provider-lmeval/)

### LlamaStack Resources
- [Configuring a Stack - LlamaStack Documentation](https://llama-stack.readthedocs.io/en/latest/distributions/configuration.html)
- [LlamaStack GitHub Repository](https://github.com/meta-llama/llama-stack)

### EleutherAI LM Evaluation Harness
- [LM Evaluation Harness GitHub](https://github.com/EleutherAI/lm-evaluation-harness)
- [Available Tasks](https://github.com/EleutherAI/lm-evaluation-harness/tree/main/lm_eval/tasks)

## Next Steps

1. **Deploy TrustyAI LMEval service** in claims-demo namespace
2. **Configure LlamaStack** to use the remote eval provider
3. **Create claims-specific evaluation dataset** for accuracy testing
4. **Run initial benchmark evaluations** (MMLU, HellaSwag)
5. **Implement backend API endpoints** for evaluation management
6. **Add frontend UI** for viewing evaluation results
7. **Set up automated evaluations** for continuous monitoring

## Status

- [x] Documentation complete
- [ ] TrustyAI LMEval deployment
- [ ] LlamaStack configuration update
- [ ] Custom claims evaluation dataset
- [ ] Backend API integration
- [ ] Frontend UI integration
- [ ] Automated evaluation pipeline
