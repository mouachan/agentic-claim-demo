# Déploiement sur OpenShift AI 3.0 - Guide Conforme

## 📚 Documentation Officielle

Ce déploiement est conforme à la documentation officielle Red Hat OpenShift AI 3.0 :
- [Working with Llama Stack](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html-single/working_with_llama_stack/)
- [Deploying a RAG stack](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html/working_with_llama_stack/deploying-a-rag-stack-in-a-project_rag)

## 🏗️ Architecture OpenShift AI 3.0

```
┌──────────────────────────────────────────────────────┐
│           OpenShift AI 3.0 Cluster                   │
│                                                       │
│  ┌────────────────────────────────────────────────┐  │
│  │  Namespace: claims-demo (DataScienceCluster)   │  │
│  │                                                 │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │ LlamaStackDistribution (CRD)             │  │  │
│  │  │ - apiVersion: llamastack.io/v1alpha1     │  │  │
│  │  │ - kind: LlamaStackDistribution           │  │  │
│  │  │                                           │  │  │
│  │  │  ┌─────────────────────────────────────┐ │  │  │
│  │  │  │ LlamaStack Server (Pod)             │ │  │  │
│  │  │  │ - Port: 8321                        │ │  │  │
│  │  │  │ - API: /inference, /embeddings      │ │  │  │
│  │  │  └────────┬────────────────────────────┘ │  │  │
│  │  │           │                               │  │  │
│  │  │           ├──> vLLM Service (externe)     │  │  │
│  │  │           │    (vos 4 modèles LLM)        │  │  │
│  │  │           │                               │  │  │
│  │  │           └──> Milvus/FAISS (vector DB)   │  │  │
│  │  │                (inline ou remote)         │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  │                                                 │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │ Serveurs MCP (Deployments standard)      │  │  │
│  │  │                                           │  │  │
│  │  │  ┌─────────────────┐                     │  │  │
│  │  │  │ OCR Server      │─┐                   │  │  │
│  │  │  └─────────────────┘ │                   │  │  │
│  │  │  ┌─────────────────┐ │                   │  │  │
│  │  │  │ RAG Server      │─┼──> LlamaStack    │  │  │
│  │  │  └─────────────────┘ │    Service        │  │  │
│  │  │  ┌─────────────────┐ │    (port 8321)    │  │  │
│  │  │  │ Orchestrator    │─┘                   │  │  │
│  │  │  └─────────────────┘                     │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  │                                                 │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │ Backend API (FastAPI)                    │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  │                                                 │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │ Frontend (React)                         │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  │                                                 │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │ PostgreSQL + pgvector                    │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

## 🎯 Différences Clés avec OpenShift AI 3.0

### ❌ Ce qui N'EXISTE PAS dans OpenShift AI 3.0

1. **Pas de CRD "MCPServer"**
   - Les serveurs MCP sont déployés comme des **Deployments Kubernetes standard**

2. **Pas de CRD "LlamaStackReference"**
   - On déploie directement **LlamaStackDistribution**
   - L'opérateur crée automatiquement le Service

3. **Pas de CRD "Guardrails" standalone**
   - Les guardrails sont implémentés dans le code applicatif
   - Pas de CRD dédié dans OpenShift AI 3.0

4. **Pas de CRD "DataScienceProject"**
   - On utilise un **namespace standard** avec les labels appropriés
   - Le DataScienceCluster s'applique au niveau cluster

### ✅ Ce qui EXISTE dans OpenShift AI 3.0

1. **LlamaStackDistribution CRD**
   ```yaml
   apiVersion: llamastack.io/v1alpha1
   kind: LlamaStackDistribution
   ```

2. **Opérateur LlamaStack**
   - Gère automatiquement le déploiement
   - Résout l'image `rh-dev` vers le bon registry
   - Crée le Service automatiquement sur port 8321

3. **Intégration vLLM**
   - LlamaStack se connecte à vos modèles vLLM existants
   - Via variables d'environnement `VLLM_URL`, `INFERENCE_MODEL`

4. **Vector Stores intégrés**
   - **Milvus inline** : Déployé automatiquement avec LlamaStack
   - **Milvus remote** : Connexion à un Milvus existant
   - **FAISS inline** : Plus simple, avec SQLite backend

## 📝 Prérequis avant Déploiement

### 1. Identifier vos Modèles LLM Existants

```bash
# Lister les services vLLM
oc get svc -A | grep vllm

# Exemple de sortie :
# ai-models    vllm-llama-3-2-3b     ClusterIP   10.0.1.100   <none>   8000/TCP
# ai-models    vllm-llama-3-2-70b    ClusterIP   10.0.1.101   <none>   8000/TCP
# ai-models    vllm-mistral-7b       ClusterIP   10.0.1.102   <none>   8000/TCP
# ai-models    vllm-embedding-model  ClusterIP   10.0.1.103   <none>   8000/TCP
```

### 2. Vérifier l'Opérateur LlamaStack

```bash
# Vérifier que l'opérateur est installé
oc get csv -n openshift-operators | grep llamastack

# Vérifier les CRDs disponibles
oc get crd | grep llamastack
```

### 3. Activer GPU Support (si nécessaire)

Selon la doc Red Hat, pour utiliser des modèles LLM avec GPU :
```bash
# Installer NVIDIA GPU Operator
# (Suivre la doc OpenShift GPU support)
```

## 🚀 Déploiement Étape par Étape

### Phase 1 : Créer le Namespace

```bash
# Créer le namespace pour la démo
oc new-project claims-demo

# Ajouter les labels appropriés
oc label namespace claims-demo \
  opendatahub.io/dashboard=true \
  modelmesh-enabled=true
```

### Phase 2 : Créer les Secrets

```bash
cd openshift/secrets

# Secret pour vLLM API token (si nécessaire)
oc create secret generic vllm-api-token \
  --from-literal=token='YOUR_VLLM_API_TOKEN' \
  -n claims-demo

# Secret pour PostgreSQL
oc create secret generic postgresql-secret \
  --from-literal=POSTGRES_USER=claims_user \
  --from-literal=POSTGRES_PASSWORD='GÉNÉRER_UN_MOT_DE_PASSE_FORT' \
  -n claims-demo

# Secret pour Milvus (si remote)
oc create secret generic milvus-credentials \
  --from-literal=username=milvus_user \
  --from-literal=password='MILVUS_PASSWORD' \
  -n claims-demo
```

### Phase 3 : Déployer LlamaStackDistribution

**Avant d'appliquer, modifiez `openshift/crds/llamastack-distribution.yaml` :**

1. Remplacez `VLLM_URL` par l'URL de votre service vLLM :
   ```yaml
   - name: VLLM_URL
     value: "http://vllm-llama-3-2.<namespace>.svc.cluster.local:8000"
   ```

2. Choisissez votre configuration de vector store :
   - **Option A** : Milvus inline (recommandé pour démarrer)
   - **Option B** : Milvus remote (si vous avez déjà Milvus)
   - **Option C** : FAISS inline (plus simple, pas de serveur externe)

3. Adaptez les noms de modèles selon vos 4 modèles :
   ```yaml
   - name: INFERENCE_MODEL
     value: "meta-llama/Llama-3.2-3b-instruct"  # Votre modèle
   ```

**Puis déployez :**

```bash
cd openshift/crds

# Déployer LlamaStack avec Milvus inline (recommandé)
oc apply -f llamastack-distribution.yaml -n claims-demo

# Attendre que le pod soit prêt
oc wait --for=condition=Ready pod -l app=llama-stack -n claims-demo --timeout=600s

# Vérifier le déploiement
oc get llamastackdistribution -n claims-demo
oc get pods -l app=llama-stack -n claims-demo
oc logs -f deployment/claims-llamastack -n claims-demo
```

### Phase 4 : Vérifier le Service LlamaStack

```bash
# Le service est créé automatiquement par l'opérateur
oc get svc -n claims-demo | grep llama

# Exemple de sortie :
# claims-llamastack   ClusterIP   10.0.2.50   <none>   8321/TCP

# Tester l'endpoint (depuis un pod debug)
oc run test-pod --rm -it --image=curlimages/curl -- \
  curl http://claims-llamastack.claims-demo.svc.cluster.local:8321/health
```

### Phase 5 : Déployer PostgreSQL

```bash
cd openshift

# Appliquer le PVC
oc apply -f pvcs/postgresql-pvc.yaml -n claims-demo

# Appliquer le StatefulSet
oc apply -f deployments/postgresql-statefulset.yaml -n claims-demo

# Appliquer le Service
oc apply -f services/postgresql-service.yaml -n claims-demo

# Attendre que PostgreSQL soit prêt
oc wait --for=condition=Ready pod -l app=postgresql -n claims-demo --timeout=300s

# Initialiser la base
POD=$(oc get pod -l app=postgresql -n claims-demo -o jsonpath='{.items[0].metadata.name}')
oc cp database/init.sql $POD:/tmp/init.sql -n claims-demo
oc exec -it $POD -n claims-demo -- psql -U claims_user -d claims_db -f /tmp/init.sql

# Charger les données de test
oc cp database/seed_data/001_sample_data.sql $POD:/tmp/seed.sql -n claims-demo
oc exec -it $POD -n claims-demo -- psql -U claims_user -d claims_db -f /tmp/seed.sql
```

### Phase 6 : Déployer les Serveurs MCP

Les serveurs MCP sont déployés comme des **Deployments Kubernetes standard**, pas des CRDs.

**Configuration de la variable d'environnement** :
```yaml
env:
  - name: LLAMASTACK_ENDPOINT
    value: "http://claims-llamastack.claims-demo.svc.cluster.local:8321"
```

```bash
cd openshift/deployments

# OCR Server
oc apply -f ocr-server-deployment.yaml -n claims-demo
oc apply -f ../services/ocr-server-service.yaml -n claims-demo

# RAG Server
oc apply -f rag-server-deployment.yaml -n claims-demo
oc apply -f ../services/rag-server-service.yaml -n claims-demo

# Orchestrator Server
oc apply -f orchestrator-server-deployment.yaml -n claims-demo
oc apply -f ../services/orchestrator-server-service.yaml -n claims-demo

# Vérifier les déploiements
oc get pods -n claims-demo | grep -E "ocr|rag|orchestrator"
```

### Phase 7 : Déployer Backend et Frontend

```bash
# Backend
oc apply -f backend-deployment.yaml -n claims-demo
oc apply -f ../services/backend-service.yaml -n claims-demo
oc apply -f ../routes/backend-route.yaml -n claims-demo

# Frontend
oc apply -f frontend-deployment.yaml -n claims-demo
oc apply -f ../services/frontend-service.yaml -n claims-demo
oc apply -f ../routes/frontend-route.yaml -n claims-demo

# Récupérer les URLs
FRONTEND_URL=$(oc get route frontend -n claims-demo -o jsonpath='{.spec.host}')
BACKEND_URL=$(oc get route backend -n claims-demo -o jsonpath='{.spec.host}')

echo "Frontend: https://$FRONTEND_URL"
echo "Backend API: https://$BACKEND_URL"
```

## 🧪 Tests

### Test 1 : Vérifier LlamaStack

```bash
# Test depuis un pod
oc run test --rm -it --image=curlimages/curl -n claims-demo -- \
  curl http://claims-llamastack:8321/models

# Devrait retourner la liste des modèles
```

### Test 2 : Vérifier les MCP Servers

```bash
# OCR Server
oc run test --rm -it --image=curlimages/curl -n claims-demo -- \
  curl http://ocr-server:8080/health

# RAG Server
oc run test --rm -it --image=curlimages/curl -n claims-demo -- \
  curl http://rag-server:8080/health

# Orchestrator
oc run test --rm -it --image=curlimages/curl -n claims-demo -- \
  curl http://orchestrator-server:8080/health
```

### Test 3 : Workflow Complet

```bash
# Depuis votre navigateur
open https://$FRONTEND_URL

# Suivre les logs en temps réel
oc logs -f deployment/backend -n claims-demo
oc logs -f deployment/ocr-server -n claims-demo
oc logs -f deployment/rag-server -n claims-demo
oc logs -f deployment/orchestrator-server -n claims-demo
```

## 📊 Monitoring

```bash
# Vérifier le statut de tous les pods
oc get pods -n claims-demo

# Vérifier les ressources LlamaStack
oc describe llamastackdistribution claims-llamastack -n claims-demo

# Logs LlamaStack
oc logs deployment/claims-llamastack -n claims-demo

# Métriques (si Prometheus activé)
oc get servicemonitor -n claims-demo
```

## 🔧 Troubleshooting

### LlamaStack ne démarre pas

```bash
# Vérifier les events
oc get events -n claims-demo --sort-by='.lastTimestamp'

# Vérifier les logs de l'opérateur
oc logs -n openshift-operators deployment/llamastack-operator

# Vérifier la configuration vLLM
oc describe llamastackdistribution claims-llamastack -n claims-demo
```

### Serveurs MCP ne peuvent pas atteindre LlamaStack

```bash
# Tester la résolution DNS
oc run test --rm -it --image=busybox -n claims-demo -- \
  nslookup claims-llamastack.claims-demo.svc.cluster.local

# Tester la connectivité
oc run test --rm -it --image=curlimages/curl -n claims-demo -- \
  curl -v http://claims-llamastack:8321/health
```

## 📚 Sources

- [Working with Llama Stack - OpenShift AI 3.0](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html-single/working_with_llama_stack/)
- [Deploying a RAG stack](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html/working_with_llama_stack/deploying-a-rag-stack-in-a-project_rag)
- [Configuring OAuth authentication](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html/working_with_llama_stack/auth-on-llama-stack_rag)
