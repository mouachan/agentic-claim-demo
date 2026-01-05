# Guide de Déploiement RAG + Vector Store

## Prérequis

- Cluster OpenShift actif avec le namespace `claims-demo`
- PostgreSQL + pgvector déployé et initialisé
- LlamaStack déployé et accessible
- `oc` CLI configuré et connecté au cluster
- `jq` installé pour le formatage JSON

## Scripts Disponibles

### 1. `deploy-rag-and-vectorstore.sh` - Déploiement Complet

**Utilisation:**
```bash
./deploy-rag-and-vectorstore.sh
```

**Ce que fait ce script:**

1. **Build du RAG Server** (Option 1: Build OpenShift)
   - Lance un build S2I sur OpenShift avec le code source local
   - Crée une nouvelle image du RAG server avec les dernières modifications
   - Alternative commentée: build local + push vers Quay.io

2. **Redémarrage du RAG Server**
   - Supprime les pods existants pour forcer le pull de la nouvelle image
   - Attend que le nouveau pod soit ready

3. **Vérification des ConfigMaps**
   - Vérifie que le ConfigMap `init-vectorstore-script` existe
   - Le crée si nécessaire avec le script `init_vectorstore.py`

4. **Initialisation du Vector Store**
   - Supprime le job précédent s'il existe
   - Lance le job `init-vectorstore` qui:
     - Se connecte à PostgreSQL
     - Crée le vector_store dans LlamaStack via API
     - Génère les embeddings pour les articles knowledge_base (si manquants)
     - Insère tous les chunks dans LlamaStack:
       - user_contracts
       - knowledge_base
       - claim_documents
   - Attend la complétion du job (max 5 minutes)

5. **Affichage des logs**
   - Montre les dernières 50 lignes de logs du job d'initialisation

6. **Tests du RAG Server**
   - Test 1: Health check (`/health/ready`)
   - Test 2: Retrieve user info pour USER001
   - Test 3: Search knowledge base

**Durée estimée:** 5-10 minutes

---

### 2. `test-rag-workflow.sh` - Tests Uniquement

**Utilisation:**
```bash
./test-rag-workflow.sh
```

**Ce que fait ce script:**

1. **Vérification des pods**
   - Liste les pods RAG server, backend et LlamaStack

2. **Test RAG Server - Health Check**
   - Vérifie que le RAG server est prêt

3. **Test RAG Server - Retrieve User Info**
   - Teste la récupération des contrats pour USER001
   - Query: "health insurance contracts"

4. **Test RAG Server - Search Knowledge Base**
   - Teste la recherche dans la base de connaissances
   - Query: "claim submission guidelines"

5. **Test Workflow End-to-End**
   - Lance le traitement d'un claim complet (claim ID 1)
   - Avec OCR + RAG activés
   - Affiche:
     - Résultat du traitement
     - Statut du claim
     - Logs de traitement par agent

**Durée estimée:** 1-2 minutes

---

## Ordre d'Exécution Recommandé

### Premier déploiement:
```bash
# 1. Déployer tout
./deploy-rag-and-vectorstore.sh

# 2. (Optionnel) Relancer les tests
./test-rag-workflow.sh
```

### Après modification du code RAG server:
```bash
# Redéployer uniquement
./deploy-rag-and-vectorstore.sh
```

### Pour tester sans redéployer:
```bash
# Tests seulement
./test-rag-workflow.sh
```

---

## Vérifications Manuelles

### Vérifier les pods
```bash
oc get pods -n claims-demo
```

### Vérifier le job d'initialisation
```bash
oc get job init-vectorstore -n claims-demo
oc logs -l job-name=init-vectorstore -n claims-demo
```

### Vérifier le vector_store dans PostgreSQL
```bash
POSTGRES_POD=$(oc get pod -n claims-demo -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
oc exec -n claims-demo ${POSTGRES_POD} -- psql -U claims_user -d claims_db -c "SELECT COUNT(*) FROM vector_store_llama_vectors;"
```

### Vérifier LlamaStack
```bash
LLAMASTACK_POD=$(oc get pod -n claims-demo -l app=claims-llamastack -o jsonpath='{.items[0].metadata.name}')
oc exec -n claims-demo ${LLAMASTACK_POD} -- curl -s http://localhost:8321/v1/vector_stores | jq .
```

---

## Logs Détaillés

### RAG Server
```bash
oc logs -f -n claims-demo -l app=rag-server
```

### Backend
```bash
oc logs -f -n claims-demo -l app=backend
```

### LlamaStack
```bash
oc logs -f -n claims-demo -l app=claims-llamastack
```

### Job d'initialisation
```bash
oc logs -n claims-demo -l job-name=init-vectorstore
```

---

## Dépannage

### Le job init-vectorstore échoue
```bash
# Voir les logs du job
oc logs -n claims-demo -l job-name=init-vectorstore

# Supprimer et relancer
oc delete job init-vectorstore -n claims-demo
oc apply -f openshift/jobs/init-vectorstore-job.yaml
```

### Le RAG server ne démarre pas
```bash
# Vérifier les logs
oc logs -n claims-demo -l app=rag-server

# Vérifier le ConfigMap LlamaStack
oc get configmap llamastack-config -n claims-demo -o yaml | grep -A 10 vector_dbs
```

### Le build OpenShift échoue
```bash
# Utiliser l'option 2 dans deploy-rag-and-vectorstore.sh
# Décommenter les lignes pour build local + push manuel
```

### Tests échouent avec timeout
```bash
# Vérifier que tous les pods sont ready
oc get pods -n claims-demo

# Vérifier les endpoints
oc get svc -n claims-demo
```

---

## Architecture du Vector Store

**Table PostgreSQL:**
- Nom: `vector_store_llama_vectors`
- Schéma: `id TEXT, document JSONB, embedding vector(768), content_text TEXT`

**Collections logiques** (via metadata.collection):
- `user_contracts` - Contrats d'assurance des utilisateurs
- `knowledge_base` - Articles de la base de connaissances
- `claim_documents` - Documents OCR des claims

**Workflow d'initialisation:**
1. PostgreSQL contient les données brutes + embeddings (générés lors du seed)
2. Script `init_vectorstore.py` lit les données depuis PostgreSQL
3. Appelle LlamaStack `/inference/embeddings` pour générer embeddings manquants
4. Insère tout via LlamaStack `/v1/vector-io/insert`
5. LlamaStack stocke dans `vector_store_llama_vectors` via son provider pgvector

**Workflow de query:**
1. RAG server reçoit une query
2. Appelle LlamaStack `/v1/vector-io/query`
3. LlamaStack fait la recherche vectorielle
4. RAG server filtre les résultats par collection (client-side)
5. Retourne les résultats au backend

---

## Métriques de Succès

- ✅ Job init-vectorstore complété sans erreur
- ✅ RAG server health check retourne `{"status":"ready"}`
- ✅ Retrieve user info retourne des contrats pertinents
- ✅ Search knowledge base retourne des articles pertinents
- ✅ Workflow end-to-end complète en < 30 secondes
- ✅ Logs RAG server montrent des timings < 10 secondes
