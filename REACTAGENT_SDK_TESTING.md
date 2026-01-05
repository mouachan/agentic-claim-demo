# Guide de Test - ReActAgent SDK

## Contexte

Actuellement, le backend utilise des **appels HTTP directs** aux APIs LlamaStack (`/v1/conversations` + `/v1/responses`) au lieu du **SDK llama-stack-client** à cause d'un **memory leak dans EventLogger**.

### Problème Observé

```
Version SDK: llama-stack-client 0.3.0rc3
Symptôme: Pod backend crash avec Exit Code 137 (OOM)
Mémoire: Même avec 8GB RAM allocation
Cause: EventLogger().log(response) consomme énormément de mémoire
Timing: Crash après ~10 secondes de processing
```

### Solution Actuelle

Appels HTTP directs au lieu du SDK → Stable, pas de leak, complète en 3-4s.

---

## Quand Retester le SDK

### Indicateurs pour retester:

1. **Nouvelle version de llama-stack-client**
   ```bash
   pip index versions llama-stack-client
   # Vérifier si >= 0.4.0 ou si release notes mentionnent:
   # - "EventLogger fix"
   # - "Memory leak fix"
   # - "OOM issue resolved"
   ```

2. **Nouvelle version de LlamaStack**
   ```bash
   oc exec -n claims-demo -l app=claims-llamastack -- \
     curl -s http://localhost:8321/health | jq .version
   # Si version > 0.3.0rc3
   ```

3. **Red Hat met à jour OpenShift AI 3.0**
   - Vérifier les release notes RHOAI
   - Chercher mentions de "LlamaStack", "memory", "agents"

---

## Procédure de Test

### 1. Backup du Code Actuel

Le code actuel (HTTP direct) est dans:
```
backend/app/api/claims.py → process_claim()
```

Le code SDK est sauvegardé dans:
```
backend/app/api/claims_reactagent_sdk_backup.py → process_claim_with_reactagent_sdk()
```

### 2. Préparer le Test

```bash
# 1. Créer une branche de test
cd /Users/mouchan/projects/agentic-claim-demo
git checkout -b test/reactagent-sdk

# 2. Copier la fonction SDK dans claims.py
# Ouvrir backend/app/api/claims.py
# Remplacer process_claim() par le contenu de process_claim_with_reactagent_sdk()
# Ou renommer process_claim() en process_claim_http()
# Et process_claim_with_reactagent_sdk() en process_claim()
```

### 3. Mettre à Jour les Dépendances

```bash
# Mettre à jour llama-stack-client
cd backend
pip install --upgrade llama-stack-client

# Vérifier la version
pip show llama-stack-client

# Mettre à jour requirements.txt si nécessaire
pip freeze | grep llama-stack-client >> requirements.txt
```

### 4. Build et Déployer pour Test

```bash
# Build l'image backend avec SDK
cd /Users/mouchan/projects/agentic-claim-demo
oc start-build backend --from-dir=backend/ --follow -n claims-demo

# Augmenter la mémoire du pod pour le test (optionnel)
oc set resources deployment/backend \
  --limits=memory=10Gi \
  --requests=memory=2Gi \
  -n claims-demo

# Redémarrer le pod
oc delete pod -l app=backend -n claims-demo
```

### 5. Monitorer la Mémoire

**Terminal 1 - Logs:**
```bash
oc logs -f -n claims-demo -l app=backend
```

**Terminal 2 - Mémoire:**
```bash
watch -n 2 'oc adm top pod -n claims-demo -l app=backend'
```

**Terminal 3 - Test:**
```bash
# Attendre que le pod soit ready
oc wait --for=condition=ready pod -l app=backend -n claims-demo --timeout=60s

# Lancer un test simple
BACKEND_POD=$(oc get pod -n claims-demo -l app=backend -o jsonpath='{.items[0].metadata.name}')

oc exec -n claims-demo ${BACKEND_POD} -- curl -s -X POST \
  http://localhost:8000/api/claims/1/process \
  -H 'Content-Type: application/json' \
  -d '{"enable_rag":true,"skip_ocr":false}' | jq .
```

### 6. Critères de Validation

#### ✅ Test RÉUSSI si:
- [ ] Processing se termine sans crash
- [ ] Mémoire reste stable (< 4GB)
- [ ] Temps de processing < 30 secondes
- [ ] Logs montrent "Claim processed via ReActAgent SDK"
- [ ] Pas de "Exit Code 137" après 5 tests consécutifs

#### ❌ Test ÉCHOUÉ si:
- [ ] Pod crash avec OOM (Exit Code 137)
- [ ] Mémoire monte au-delà de 8GB
- [ ] Timeout après 2 minutes
- [ ] Erreurs dans les logs liées à EventLogger

### 7. Tests Multiples

```bash
# Lancer 10 tests consécutifs
for i in {1..10}; do
  echo "=== Test $i/10 ==="
  oc exec -n claims-demo ${BACKEND_POD} -- curl -s -X POST \
    http://localhost:8000/api/claims/1/process \
    -H 'Content-Type: application/json' \
    -d '{"enable_rag":true,"skip_ocr":false}' | jq .status

  # Vérifier la mémoire
  oc adm top pod -n claims-demo -l app=backend

  sleep 10
done
```

### 8. Décision

**Si TOUS les tests passent:**
```bash
# Merger la branche
git add backend/app/api/claims.py
git commit -m "Migrate to ReActAgent SDK (memory leak fixed)"
git checkout main
git merge test/reactagent-sdk

# Supprimer le backup
rm backend/app/api/claims_reactagent_sdk_backup.py
```

**Si UN SEUL test échoue:**
```bash
# Revenir à la version HTTP
git checkout main

# Documenter l'échec
echo "Tested llama-stack-client $(pip show llama-stack-client | grep Version) on $(date)" >> SDK_TEST_HISTORY.md
echo "Result: FAILED - Still OOM" >> SDK_TEST_HISTORY.md
```

---

## Différences Clés SDK vs HTTP

| Aspect | SDK (ReActAgent) | HTTP Direct (Actuel) |
|--------|------------------|----------------------|
| **Code** | Plus pythonic, propre | Plus verbose |
| **Type hints** | Complets via SDK | Dictionnaires JSON |
| **Debugging** | EventLogger (si pas de leak) | Logs manuels |
| **Mémoire** | ❌ Leak dans 0.3.0rc3 | ✅ Stable |
| **Performance** | Potentiellement meilleur | 3-4s actuellement |
| **Maintenance** | Dépend du SDK | Indépendant |

---

## Code Comparison

### Version SDK (backup)
```python
from llama_stack_client import LlamaStackClient
from llama_stack_client.lib.agents.agent import Agent
from llama_stack_client.lib.agents.event_logger import EventLogger
from llama_stack_client.types.agent_create_params import AgentConfig

client = LlamaStackClient(base_url=settings.llamastack_endpoint)
agent = Agent(client=client, agent_config=AgentConfig(...))
session_id = agent.create_session(...)
response = agent.create_turn(messages=[...], session_id=session_id, stream=True)

event_logger = EventLogger()
for chunk in response:
    event_logger.log(chunk)  # ❌ Memory leak here

final_response = event_logger.get_response()
```

### Version HTTP (actuelle)
```python
import httpx

async with httpx.AsyncClient(timeout=120.0) as http_client:
    # Create conversation
    conv_response = await http_client.post(
        f"{settings.llamastack_endpoint}/v1/conversations",
        json={"name": f"claim_{claim_id}"}
    )
    conversation_id = conv_response.json()["conversation_id"]

    # Get response
    agent_response = await http_client.post(
        f"{settings.llamastack_endpoint}/v1/responses",
        json={
            "model": settings.llamastack_default_model,
            "conversation_id": conversation_id,
            "messages": [...],
            "tools": mcp_tools,
            "stream": False
        }
    )

    final_response = agent_response.json()["choices"][0]["message"]["content"]
```

---

## Monitoring Avancé

### Prometheus Queries (si disponible)

```promql
# Memory usage
container_memory_usage_bytes{pod=~"backend-.*",namespace="claims-demo"}

# Memory limit
container_spec_memory_limit_bytes{pod=~"backend-.*",namespace="claims-demo"}

# OOM kills
kube_pod_container_status_terminated_reason{reason="OOMKilled",namespace="claims-demo"}
```

### Grafana Dashboard

Créer un dashboard avec:
1. Memory usage over time
2. Request count
3. Average response time
4. Error rate
5. OOM kills count

---

## Historique des Tests

Créer un fichier `SDK_TEST_HISTORY.md` pour tracker les tentatives:

```markdown
# Historique des Tests ReActAgent SDK

## 2024-12-30 - Test Initial
- Version: llama-stack-client 0.3.0rc3
- Résultat: FAILED
- Raison: OOM avec EventLogger.log()
- RAM allouée: 8GB
- Action: Migration vers HTTP direct

## (Future date) - Retest après update
- Version: llama-stack-client X.X.X
- Résultat: ...
- Notes: ...
```

---

## Rollback Rapide

Si le SDK crash en production:

```bash
# 1. Rollback immédiat
oc rollout undo deployment/backend -n claims-demo

# 2. Ou redeploy la version HTTP
git checkout main
oc start-build backend --from-dir=backend/ --follow -n claims-demo

# 3. Vérifier
oc logs -f -n claims-demo -l app=backend
```

---

## Ressources

- **SDK Docs**: https://github.com/meta-llama/llama-stack-client-python
- **LlamaStack API**: https://llamastack.github.io/docs/
- **Issues SDK**: https://github.com/meta-llama/llama-stack-client-python/issues
- **RHOAI Docs**: https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/
