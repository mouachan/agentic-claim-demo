# État de la Session et Tâches Restantes

Date: 2025-12-24
Session suivante: À continuer

## ✅ Réalisé Aujourd'hui

### 1. Déploiement Llama 3.2 3B avec Tool Calling
- ✅ Identifié et résolu le problème CUDA Error 803
- ✅ Trouvé la bonne image vLLM: `registry.redhat.io/rhaiis/vllm-cuda-rhel9:latest` (v3.2.5)
- ✅ Créé répertoire complet de déploiement: `openshift/llama-32-3b-instruct/`
  - 01-pvc.yaml
  - 02-secret-hf-token.yaml (avec placeholder)
  - 03-model-download-job.yaml
  - 04-servingruntime.yaml (avec nouvelle image CUDA 12.9)
  - 05-inferenceservice.yaml (avec tool calling activé)
  - CRD-InferenceService.yaml (récupéré du cluster)
  - CRD-ServingRuntime.yaml (récupéré du cluster)
  - README.md complet avec documentation investigation
- ✅ Llama 3.2 3B fonctionne correctement avec tool calling

### 2. Orchestrateur - Fix Pydantic
- ✅ Identifié l'erreur de validation Pydantic
- ✅ Corrigé les noms de champs dans `llamastack_agent_orchestrator.py`:
  - `agent_name` → `agent` (ligne 208)
  - `output_data` → `output` (ligne 211)
- ✅ ConfigMap mis à jour
- ✅ Pod orchestrateur redémarré

### 3. Tests Tool Calling
- ✅ Test simple calculator: SUCCESS
- ✅ Test claim processing: Tool calling fonctionne (4 tools appelés dans le bon ordre)
  1. ocr_document
  2. retrieve_user_info
  3. retrieve_similar_claims
  4. make_final_decision

## ⚠️ Problèmes Restants à Résoudre

### Problème 1: PostgreSQL ENUM - Noms des Steps
**Erreur:**
```
ERROR: invalid input value for enum processing_step: "ocr_document"
```

**Cause:**
La base de données PostgreSQL a un ENUM `processing_step` qui ne contient pas les nouveaux noms de steps générés par l'orchestrateur intelligent.

**Steps actuels dans la DB:**
- Probablement: `ocr`, `guardrails`, `rag`, `decision`

**Nouveaux steps nécessaires:**
- `ocr_document`
- `retrieve_user_info`
- `retrieve_similar_claims`
- `make_final_decision`

**Solutions possibles:**
1. **Option A (Recommandée):** Ajouter les nouveaux noms au ENUM PostgreSQL
   ```sql
   ALTER TYPE processing_step ADD VALUE 'ocr_document';
   ALTER TYPE processing_step ADD VALUE 'retrieve_user_info';
   ALTER TYPE processing_step ADD VALUE 'retrieve_similar_claims';
   ALTER TYPE processing_step ADD VALUE 'make_final_decision';
   ```

2. **Option B:** Mapper les nouveaux noms vers les anciens dans le code
   - Dans `server.py`, avant d'écrire dans la DB
   - Ajouter un dictionnaire de mapping:
     ```python
     STEP_NAME_MAPPING = {
         "ocr_document": "ocr",
         "retrieve_user_info": "rag",
         "retrieve_similar_claims": "rag",
         "make_final_decision": "decision"
     }
     ```

3. **Option C:** Supprimer le ENUM et utiliser VARCHAR
   - Plus flexible mais moins de validation

**Fichier à modifier:** `/Users/mouchan/projects/agentic-claim-demo/database/init.sql` ou migration Alembic

### Problème 2: Backend API Claims Endpoint
**Observation:**
- Backend est accessible: `https://backend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/`
- Root endpoint fonctionne (retourne status healthy)
- `/api/claims` retourne 404 "Not Found"
- `/docs` retourne aussi 404

**Causes possibles:**
1. Les routes API ne sont pas configurées correctement
2. Le préfixe `/api` n'est pas appliqué
3. Le backend n'a pas été déployé avec les bons endpoints

**À investiguer:**
- Vérifier le fichier `backend/app/main.py` pour voir comment les routes sont configurées
- Vérifier si `app.include_router(claims.router, prefix="/api")` est présent
- Relire les logs backend pour voir si les routes sont bien enregistrées au démarrage

**Fichiers à vérifier:**
- `/Users/mouchan/projects/agentic-claim-demo/backend/app/main.py`
- `/Users/mouchan/projects/agentic-claim-demo/backend/app/api/claims.py`

### Problème 3: Test End-to-End Incomplet
Impossible de tester le traitement complet d'un claim car:
- L'endpoint `/api/claims` n'est pas accessible
- Besoin de pouvoir lister les claims
- Besoin de pouvoir déclencher le traitement

## 📋 Tâches pour la Prochaine Session

### Priorité 1: Fix PostgreSQL ENUM
- [ ] Se connecter à PostgreSQL
- [ ] Vérifier les valeurs actuelles du ENUM `processing_step`
- [ ] Choisir entre Option A, B ou C
- [ ] Appliquer la solution (ALTER TYPE ou modifier le code)
- [ ] Tester que le logging des steps fonctionne

### Priorité 2: Fix Backend API Routes
- [ ] Vérifier `backend/app/main.py`
- [ ] S'assurer que les routes `/api/claims` sont bien configurées
- [ ] Vérifier les logs de démarrage du backend
- [ ] Redéployer le backend si nécessaire
- [ ] Tester `GET /api/claims`

### Priorité 3: Test End-to-End Complet
- [ ] Lister les claims via l'API
- [ ] Déclencher le traitement d'un claim
- [ ] Vérifier les logs de l'orchestrateur
- [ ] Vérifier que les steps sont bien enregistrés dans la DB
- [ ] Vérifier le résultat final dans la DB
- [ ] Tester via le frontend si disponible

### Priorité 4: Documentation
- [ ] Mettre à jour le README principal avec les dernières modifications
- [ ] Documenter la solution au problème ENUM
- [ ] Ajouter des exemples de requêtes API

## 🔧 Commandes Utiles pour Demain

### PostgreSQL
```bash
# Se connecter à PostgreSQL
oc exec -it -n claims-demo statefulset/postgresql -- psql -U claimsuser -d claimsdb

# Vérifier l'ENUM actuel
\dT+ processing_step

# Lister les claims
SELECT id, user_id, status FROM claims LIMIT 5;

# Lister les processing logs
SELECT * FROM processing_logs ORDER BY timestamp DESC LIMIT 10;
```

### Backend
```bash
# Logs backend
oc logs -n claims-demo deployment/backend --tail=100

# Logs orchestrateur
oc logs -n claims-demo deployment/orchestrator-server --tail=100

# Redéployer backend
oc delete pods -l app=backend -n claims-demo
```

### Test API
```bash
# Root endpoint
curl -s https://backend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/ | jq '.'

# Claims endpoint (à fix)
curl -s https://backend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/api/claims | jq '.'

# Test traitement claim
curl -X POST https://backend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/api/claims/<CLAIM_ID>/process \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Llama Tool Calling Test
```bash
# Test simple
LLAMA_URL="llama-instruct-32-3b-llama-instruct-32-3b-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com"

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
  }' | jq '.choices[0].message.tool_calls'
```

## 📊 État du Système

### Composants Fonctionnels ✅
- PostgreSQL + pgvector: Running
- Llama 3.2 3B InferenceService: Running (tool calling activé)
- Orchestrateur MCP: Running (code fixé)
- OCR Server: Running
- RAG Server: Running
- Backend: Running (mais routes API non accessibles)
- Frontend: Running (mais non testé)

### Composants à Vérifier ⚠️
- Backend API routes (404 sur /api/claims)
- PostgreSQL ENUM (incompatible avec nouveaux step names)
- Intégration end-to-end

## 📁 Fichiers Importants

### Modifiés Aujourd'hui
- `/Users/mouchan/projects/agentic-claim-demo/backend/mcp_servers/orchestrator_server/llamastack_agent_orchestrator.py`
  - Ligne 23: LLM_ENDPOINT changé de Mistral vers Llama
  - Ligne 208: `agent_name` → `agent`
  - Ligne 211: `output_data` → `output`

### Créés Aujourd'hui
- `/Users/mouchan/projects/agentic-claim-demo/openshift/llama-32-3b-instruct/` (tout le répertoire)
  - 01-pvc.yaml
  - 02-secret-hf-token.yaml
  - 03-model-download-job.yaml
  - 04-servingruntime.yaml
  - 05-inferenceservice.yaml
  - CRD-InferenceService.yaml
  - CRD-ServingRuntime.yaml
  - README.md (documentation complète)

### À Examiner Demain
- `/Users/mouchan/projects/agentic-claim-demo/backend/app/main.py`
- `/Users/mouchan/projects/agentic-claim-demo/backend/app/api/claims.py`
- `/Users/mouchan/projects/agentic-claim-demo/database/init.sql`

## 🎯 Objectif Final

Réussir un traitement end-to-end complet:
1. Frontend → Backend `/api/claims/{id}/process`
2. Backend → Orchestrateur MCP
3. Orchestrateur → LLM Llama 3.2 3B (tool calling)
4. LLM → Orchestrateur avec liste de tools à appeler
5. Orchestrateur → Appel séquentiel des tools (OCR, RAG, etc.)
6. Orchestrateur → Retour résultat au Backend
7. Backend → Sauvegarde steps dans PostgreSQL (ENUM fixé)
8. Backend → Retour résultat au Frontend
9. Frontend → Affichage résultat + logs de traitement

---

**Status:** 70% complété
**Bloqueurs:** PostgreSQL ENUM + Backend API routes
**Prochaine action:** Fix PostgreSQL ENUM puis test API endpoints

Bonne nuit! 🌙
