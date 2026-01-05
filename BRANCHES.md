# Guide des Branches

## Branches Disponibles

### `main` - ReActAgent SDK (Version Actuelle)
**Utilise:** `llama-stack-client` SDK avec ReActAgent

**Code:**
```python
from llama_stack_client import LlamaStackClient
from llama_stack_client.lib.agents.agent import Agent
from llama_stack_client.lib.agents.event_logger import EventLogger

client = LlamaStackClient(base_url=settings.llamastack_endpoint)
agent = Agent(client=client, agent_config=AgentConfig(...))
response = agent.create_turn(messages=[...], session_id=session_id, stream=True)

event_logger = EventLogger()
for chunk in response:
    event_logger.log(chunk)

final_response = event_logger.get_response()
```

**Avantages:**
- ✅ Code pythonic et propre
- ✅ Type hints complets
- ✅ Gestion automatique des sessions
- ✅ EventLogger pour debugging

**Inconvénients:**
- ⚠️ Potentiel memory leak dans EventLogger (version 0.3.0rc3)
- ⚠️ Risque d'OOM sur gros volumes
- ⚠️ Dépend de la stabilité du SDK

**Quand utiliser:**
- Pour tester la version officielle du SDK
- Après mise à jour de llama-stack-client (>= 0.4.0)
- En développement local avec monitoring mémoire

---

### `http-response-api` - HTTP Direct (Version Stable)
**Utilise:** Appels HTTP directs à LlamaStack

**Code:**
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

**Avantages:**
- ✅ Pas de memory leak
- ✅ Stable et prévisible
- ✅ Mémoire constante (~2-3GB)
- ✅ Performance: 3-4 secondes
- ✅ Facile à debugger (requêtes brutes)

**Inconvénients:**
- ⚠️ Code plus verbose
- ⚠️ Pas de type hints automatiques
- ⚠️ Gestion manuelle des sessions

**Quand utiliser:**
- En production
- Si le SDK cause des OOM
- Pour performance garantie
- Pour debugging approfondi

---

## Caractéristiques Communes (Les Deux Branches)

Les deux branches incluent **toutes les corrections du vector store:**

### ✅ RAG Server Optimisé
- Endpoint corrigé: `/v1/vector-io/query`
- Récupération dynamique du `vector_store_id`
- Filtrage client-side par collection
- Timing logs pour détecter timeouts

### ✅ OCR Optimisé
- Compression d'image: 70% resize + JPEG 85
- Réduit le temps de traitement: 12s → 8s
- Reste sous le timeout de 10s

### ✅ Vector Store Initialization
- Script `init_vectorstore.py` pour peupler LlamaStack
- Kubernetes Job pour automatisation
- Génération d'embeddings pour knowledge_base
- Insertion via `/v1/vector-io/insert`

### ✅ Configuration LlamaStack
- Section `vector_dbs` dans le ConfigMap
- Provider pgvector configuré
- Table `vector_store_llama_vectors` créée

### ✅ Scripts d'Automatisation
- `deploy-rag-and-vectorstore.sh` - Déploiement complet
- `test-rag-workflow.sh` - Tests automatisés
- `DEPLOYMENT.md` - Documentation complète

---

## Comparaison des Performances

| Métrique | ReActAgent SDK (main) | HTTP Direct (http-response-api) |
|----------|------------------------|----------------------------------|
| **Temps de traitement** | ~10s (avec EventLogger) | 3-4s |
| **Mémoire utilisée** | 6-8GB (avec leak) | 2-3GB |
| **Stabilité** | ⚠️ OOM possible | ✅ Stable |
| **Code** | ✅ Propre et pythonic | ⚠️ Verbose |
| **Type hints** | ✅ Complet | ⚠️ Manuel |
| **Debugging** | ✅ EventLogger | ✅ Logs HTTP |

---

## Changer de Branche

### Passer à la version HTTP (Stable)
```bash
git checkout http-response-api

# Rebuild backend
oc start-build backend --from-dir=backend/ --follow -n claims-demo

# Redémarrer
oc delete pod -l app=backend -n claims-demo
```

### Revenir à la version SDK
```bash
git checkout main

# Rebuild backend
oc start-build backend --from-dir=backend/ --follow -n claims-demo

# Redémarrer ET monitorer la mémoire
oc delete pod -l app=backend -n claims-demo
watch -n 2 'oc adm top pod -n claims-demo -l app=backend'
```

---

## Recommandation

### Pour Production Actuelle
👉 **Utiliser `http-response-api`**
- Stable et testé
- Pas de risque d'OOM
- Performance garantie

### Pour Développement/Test
👉 **Utiliser `main`**
- Tester les nouvelles versions du SDK
- Contribuer aux rapports de bugs
- Valider les fixes upstream

### Après Mise à Jour LlamaStack
👉 **Retester `main`**
- Vérifier les release notes
- Tester avec monitoring mémoire
- Migrer si stable

---

## Historique des Problèmes

### 2024-12 - Memory Leak EventLogger
**Version:** llama-stack-client 0.3.0rc3
**Symptôme:** OOM Exit Code 137 même avec 8GB RAM
**Cause:** EventLogger.log() accumule trop de données en mémoire
**Solution:** Migration vers HTTP direct (branche http-response-api)

### À surveiller
- Nouvelle version de llama-stack-client (>= 0.4.0)
- Fix du memory leak dans EventLogger
- Release notes mentionnant "memory", "OOM", ou "EventLogger"

---

## Liens Utiles

- **SDK GitHub:** https://github.com/meta-llama/llama-stack-client-python
- **LlamaStack Docs:** https://llamastack.github.io/docs/
- **Guide de Test SDK:** `REACTAGENT_SDK_TESTING.md`
- **Guide Déploiement:** `DEPLOYMENT.md`
