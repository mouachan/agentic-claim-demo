# Déploiement Llama 3.2 3B Instruct avec Tool Calling sur OpenShift AI

Ce répertoire contient tous les manifests nécessaires pour déployer le modèle **Llama 3.2 3B Instruct** avec support du **tool calling** sur OpenShift AI 3.0.

## Contexte: Résolution du Problème CUDA Driver

### Problème Rencontré

Les pods vLLM crashaient au démarrage avec l'erreur suivante:
```
RuntimeError: Unexpected error from cudaGetDeviceCount().
Error 803: system has unsupported display driver / cuda driver combination
```

### Investigation

#### 1. Identification du Problème

**Commande utilisée:**
```bash
oc logs llama-instruct-32-3b-predictor-<pod-id> -n llama-instruct-32-3b-demo
```

**Erreur détectée:**
```
(EngineCore_DP0 pid=153) RuntimeError: system has unsupported display driver / cuda driver combination
```

L'erreur se produisait lors de l'initialisation de flash-attention dans vLLM v0.11.0+rhai1.

#### 2. Vérification de l'Image Utilisée

**Commande:**
```bash
oc get deployment llama-instruct-32-3b-predictor -n llama-instruct-32-3b-demo -o yaml | grep "image:"
```

**Résultat:**
```yaml
image: registry.redhat.io/rhaiis/vllm-cuda-rhel9@sha256:ad756c01ec99a99cc7d93401c41b8d92ca96fb1ab7c5262919d818f2be4f3768
```

#### 3. Vérification des GPUs Disponibles

**Commande:**
```bash
oc get nodes -o json | jq -r '.items[] | select(.status.allocatable["nvidia.com/gpu"] != null) | "\(.metadata.name)\t\(.status.allocatable["nvidia.com/gpu"])"'
```

**Résultat:**
```
Node ip-10-0-32-61: 4 GPUs (NVIDIA L4) - CUDA driver 580.105.08, runtime 13.0
Node ip-10-0-43-47: 4 GPUs (NVIDIA L4) - CUDA driver 570.124.06, runtime 12.8
```

**Problème identifié:** Les pods tentaient de démarrer sur le node avec CUDA driver 580, mais l'image vLLM était compilée avec une ancienne version de flash-attention incompatible.

#### 4. Recherche de la Nouvelle Image

**Commande utilisée pour interroger le registre Red Hat:**
```bash
curl -s "https://catalog.redhat.com/api/containers/v1/repositories/registry/registry.access.redhat.com/repository/rhaiis/vllm-cuda-rhel9/images" | jq '.data[] | {version: .parsed_data.labels[] | select(.name=="version").value, cuda: .parsed_data.env_variables[] | select(contains("CUDA_VERSION")), created: .creation_date}'
```

**Images trouvées:**

| Version | Date Création | CUDA Version | SHA256 |
|---------|---------------|--------------|--------|
| **3.2.5 (latest)** | **2025-12-18** | **12.9.1** | `916c8ce1fef3...` |
| 3.2.0 | 2025-07-21 | 12.x | `bc4e842f04f7...` |
| 3.1.0 | 2025-07-07 | 12.x | `771bc45e13c5...` |
| 3.0.0 | 2025-05-16 | 12.x | `2205c7f9e2a8...` |

**Solution:** Utiliser `registry.redhat.io/rhaiis/vllm-cuda-rhel9:latest` (version 3.2.5 avec CUDA 12.9.1)

Cette version est compatible avec le driver CUDA 580 car:
- Elle inclut vLLM v0.11.2+rhai5 (au lieu de v0.11.0+rhai1)
- Flash-attention mis à jour pour supporter les nouveaux drivers
- Support complet de CUDA 12.9.1

#### 5. Application de la Correction

**Commande de patch:**
```bash
oc patch deployment llama-instruct-32-3b-predictor \
  -n llama-instruct-32-3b-demo \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/image", "value": "registry.redhat.io/rhaiis/vllm-cuda-rhel9:latest"}]'
```

**Redémarrage des pods:**
```bash
oc delete pods -l serving.kserve.io/inferenceservice=llama-instruct-32-3b -n llama-instruct-32-3b-demo
```

**Vérification:**
```bash
oc logs <new-pod-name> -n llama-instruct-32-3b-demo | grep -i "Using FLASH_ATTN"
```

**Résultat attendu:**
```
INFO 12-23 23:45:20 [cuda.py:427] Using FLASH_ATTN backend.
INFO:     Application startup complete.
```

✅ **Succès!** Le pod démarre correctement avec la nouvelle image.

---

## Prérequis

1. **Namespace créé:**
   ```bash
   oc new-project llama-instruct-32-3b-demo
   ```

2. **Token HuggingFace:** Obtenir un token depuis https://huggingface.co/settings/tokens avec accès au modèle `meta-llama/Llama-3.2-3B-Instruct`

3. **Accès GPU:** Cluster OpenShift avec des nodes GPU (NVIDIA L4 ou équivalent)

---

## Architecture

```
┌─────────────────────────────────────────────┐
│   PVC (20Gi)                                │
│   llama32-3b-instruct-model                 │
│   ├─ /llama32-3b-instruct/                  │
│   │   └─ [Model files from HuggingFace]     │
└─────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────┐
│   Job: download-llama32-3b-instruct-hf      │
│   Downloads model from HuggingFace to PVC   │
└─────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────┐
│   ServingRuntime                            │
│   - vLLM v0.11.2+rhai5                      │
│   - Image: rhaiis/vllm-cuda-rhel9:latest    │
│   - CUDA 12.9.1 compatible                  │
└─────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────┐
│   InferenceService                          │
│   - Tool calling enabled                    │
│   - llama3_json parser                      │
│   - Auto tool choice                        │
│   - Served as: llama-instruct-32-3b         │
└─────────────────────────────────────────────┘
```

---

## Ordre de Déploiement

### 1. Créer le PVC

```bash
oc apply -f 01-pvc.yaml
```

**Vérification:**
```bash
oc get pvc llama32-3b-instruct-model -n llama-instruct-32-3b-demo
```

### 2. Créer le Secret HuggingFace

**⚠️ IMPORTANT:** Modifier le fichier `02-secret-hf-token.yaml` et remplacer le placeholder par votre vrai token HuggingFace.

```yaml
stringData:
  token: "hf_YOUR_REAL_TOKEN_HERE"  # Remplacer ici
```

Puis appliquer:
```bash
oc apply -f 02-secret-hf-token.yaml
```

### 3. Lancer le Téléchargement du Modèle

```bash
oc apply -f 03-model-download-job.yaml
```

**Suivre la progression:**
```bash
oc logs -f job/download-llama32-3b-instruct-hf -n llama-instruct-32-3b-demo
```

**Durée estimée:** 10-15 minutes (modèle ~6GB)

**Vérification:**
```bash
oc get jobs -n llama-instruct-32-3b-demo
# STATUS should be "Complete"
```

### 4. Déployer le ServingRuntime

```bash
oc apply -f 04-servingruntime.yaml
```

**Vérification:**
```bash
oc get servingruntime llama-instruct-32-3b -n llama-instruct-32-3b-demo
```

### 5. Déployer l'InferenceService

```bash
oc apply -f 05-inferenceservice.yaml
```

**Vérification:**
```bash
oc get inferenceservice llama-instruct-32-3b -n llama-instruct-32-3b-demo
```

**Attendre que le statut soit READY:**
```bash
oc wait --for=condition=Ready inferenceservice/llama-instruct-32-3b \
  -n llama-instruct-32-3b-demo --timeout=10m
```

---

## Vérification du Déploiement

### 1. Vérifier les Pods

```bash
oc get pods -n llama-instruct-32-3b-demo | grep predictor
```

**Résultat attendu:**
```
llama-instruct-32-3b-predictor-xxxxx   1/1     Running   0   5m
```

### 2. Vérifier les Logs

```bash
oc logs -l serving.kserve.io/inferenceservice=llama-instruct-32-3b -n llama-instruct-32-3b-demo | grep -E "(vLLM|FLASH_ATTN|tool)"
```

**Messages importants:**
```
INFO: vLLM API server version 0.11.2+rhai5
INFO: Using FLASH_ATTN backend
INFO: "auto" tool choice has been enabled
INFO: Application startup complete
```

### 3. Obtenir l'URL du Service

```bash
oc get route llama-instruct-32-3b -n llama-instruct-32-3b-demo -o jsonpath='{.spec.host}'
```

---

## Test du Tool Calling

### Test Simple

```bash
LLAMA_URL=$(oc get route llama-instruct-32-3b -n llama-instruct-32-3b-demo -o jsonpath='{.spec.host}')

curl -X POST "https://$LLAMA_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-instruct-32-3b",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "calculator",
        "description": "Calculate math expressions",
        "parameters": {
          "type": "object",
          "properties": {
            "expression": {"type": "string"}
          },
          "required": ["expression"]
        }
      }
    }],
    "tool_choice": "auto",
    "max_tokens": 200
  }'
```

### Test avec Tool Call

```bash
curl -X POST "https://$LLAMA_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-instruct-32-3b",
    "messages": [{"role": "user", "content": "Extract the text from this PDF: /claim_documents/claim_auto_001.pdf"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "ocr_document",
        "description": "Extract text from a PDF document",
        "parameters": {
          "type": "object",
          "properties": {
            "document_path": {"type": "string"}
          },
          "required": ["document_path"]
        }
      }
    }],
    "tool_choice": "auto"
  }'
```

**Réponse attendue avec tool_calls:**
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "tool_calls": [{
        "function": {
          "name": "ocr_document",
          "arguments": "{\"document_path\": \"/claim_documents/claim_auto_001.pdf\"}"
        }
      }]
    }
  }]
}
```

---

## Configuration du Tool Calling

Le modèle est configuré avec les arguments vLLM suivants:

| Argument | Valeur | Description |
|----------|--------|-------------|
| `--enable-auto-tool-choice` | (flag) | Active la sélection automatique des tools |
| `--tool-call-parser` | `llama3_json` | Parser JSON spécifique à Llama 3 |
| `--chat-template` | `/opt/app-root/template/tool_chat_template_llama3.2_json.jinja` | Template de chat avec support des tools |

Ces paramètres permettent au modèle de:
1. Détecter quand un tool doit être appelé
2. Extraire les paramètres au format JSON
3. Retourner les tool_calls dans la réponse OpenAI-compatible

---

## Intégration avec l'Orchestrateur

Pour utiliser ce modèle dans l'orchestrateur de claims:

**Fichier:** `backend/mcp_servers/orchestrator_server/llamastack_agent_orchestrator.py`

```python
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT",
    "https://llama-instruct-32-3b-llama-instruct-32-3b-demo.apps.cluster-xxx.com/v1/chat/completions")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama-instruct-32-3b")
```

---

## Dépannage

### Problème: Pod en CrashLoopBackOff

**Commande:**
```bash
oc logs <pod-name> -n llama-instruct-32-3b-demo --tail=100
```

**Erreur commune:** `Error 803: system has unsupported display driver / cuda driver combination`

**Solution:** Vérifier que l'image est bien `registry.redhat.io/rhaiis/vllm-cuda-rhel9:latest`

### Problème: Model Load Failed

**Vérification du PVC:**
```bash
oc exec -it deployment/llama-instruct-32-3b-predictor -n llama-instruct-32-3b-demo -- ls -lah /mnt/models/llama32-3b-instruct/
```

**Doit contenir:**
- `config.json`
- `tokenizer.json`
- `*.safetensors` files

### Problème: Tool Calling ne fonctionne pas

**Vérifier les arguments vLLM:**
```bash
oc get inferenceservice llama-instruct-32-3b -n llama-instruct-32-3b-demo -o yaml | grep -A 10 "args:"
```

**Doit inclure:**
```yaml
- --enable-auto-tool-choice
- --tool-call-parser
- llama3_json
- --chat-template=/opt/app-root/template/tool_chat_template_llama3.2_json.jinja
```

---

## Nettoyage

```bash
# Supprimer l'InferenceService
oc delete inferenceservice llama-instruct-32-3b -n llama-instruct-32-3b-demo

# Supprimer le ServingRuntime
oc delete servingruntime llama-instruct-32-3b -n llama-instruct-32-3b-demo

# Supprimer le Job de téléchargement
oc delete job download-llama32-3b-instruct-hf -n llama-instruct-32-3b-demo

# Supprimer le PVC (⚠️ supprime le modèle téléchargé)
oc delete pvc llama32-3b-instruct-model -n llama-instruct-32-3b-demo

# Supprimer le secret
oc delete secret hf-token -n llama-instruct-32-3b-demo
```

---

## Références

- **Red Hat AI Inference Server:** https://catalog.redhat.com/software/containers/rhaiis/vllm-cuda-rhel9
- **vLLM Documentation:** https://docs.vllm.ai/
- **Llama 3.2 Model Card:** https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct
- **KServe InferenceService:** https://kserve.github.io/website/latest/

---

## Historique des Versions

| Date | Version Image | vLLM Version | Changement |
|------|---------------|--------------|------------|
| 2025-12-23 | `rhaiis/vllm-cuda-rhel9:latest` (3.2.5) | v0.11.2+rhai5 | Fix CUDA 580 compatibility |
| 2025-11-14 | `rhaiis/vllm-cuda-rhel9@sha256:ad756c01...` (3.0.0) | v0.11.0+rhai1 | Version initiale (incompatible CUDA 580) |
