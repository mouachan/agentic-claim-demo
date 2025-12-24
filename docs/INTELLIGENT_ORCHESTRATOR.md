# Guide: Orchestrateur Intelligent avec LLM

## Concept de l'Orchestrateur Intelligent

Un orchestrateur intelligent utilise un **LLM pour décider dynamiquement**:
1. **Quels agents** appeler
2. **Dans quel ordre** les appeler
3. **Avec quels paramètres**
4. **Quand s'arrêter** (condition de terminaison)

## Architecture: 3 Approches

### Approche 1: Code Statique + LLM pour Paramètres (Actuel - Basique)
```
[Orchestrateur]
    ├─> Toujours: OCR
    ├─> Toujours: Guardrails
    ├─> Toujours: RAG
    └─> Toujours: LLM Decision
```
**Limites**: Ordre fixe, pas d'adaptation

### Approche 2: LLM Décide de l'Ordre (Intermédiaire)
```
[Orchestrateur] --> [LLM: Planning]
    ├─> "Pour ce claim AUTO, appelle: OCR → Guardrails → RAG → Decision"
    └─> Exécute le plan
```
**Avantage**: Ordre adaptatif selon le type de claim

### Approche 3: LLM Agent Loop (Avancé - Recommandé)
```
[Orchestrateur Intelligent]
    Loop:
        1. LLM analyse l'état actuel
        2. LLM choisit le prochain agent à appeler
        3. Exécute l'agent
        4. LLM décide: continuer ou terminer?
    End Loop
```
**Avantage**: Totalement dynamique, peut s'adapter en cours de route

---

## Implémentation: Orchestrateur Intelligent (Approche 3)

### 1. Prompt System pour l'Orchestrateur

```python
ORCHESTRATOR_SYSTEM_PROMPT = """Tu es un orchestrateur intelligent pour le traitement de claims d'assurance.

## Agents Disponibles:
1. **ocr_agent**: Extrait le texte d'un document PDF
   - Input: document_path
   - Output: raw_text, structured_data (fields extraits)
   - Utilise quand: Document non encore traité

2. **guardrails_agent**: Vérifie les données sensibles
   - Input: text, structured_data
   - Output: has_pii, sensitive_data_detected, cleared
   - Utilise quand: Après OCR, avant traitement sensible

3. **rag_agent**: Récupère informations utilisateur et claims similaires
   - Input: user_id, claim_text
   - Output: user_contracts, similar_claims
   - Utilise quand: Besoin de contexte historique

4. **fraud_detection_agent**: Détecte les fraudes potentielles
   - Input: claim_data, user_history
   - Output: fraud_score, suspicious_patterns
   - Utilise quand: Montant élevé ou patterns suspects

5. **policy_checker_agent**: Vérifie la conformité aux polices
   - Input: claim_data, user_contracts
   - Output: coverage_applies, policy_violations
   - Utilise quand: Après RAG, avant décision finale

6. **llm_decision_agent**: Décision finale
   - Input: all_gathered_data
   - Output: decision (approve/deny/manual_review), reasoning
   - Utilise quand: Toutes les données nécessaires collectées

## Instructions:
1. Analyse l'état actuel du traitement
2. Choisis le PROCHAIN agent le plus approprié
3. Justifie ton choix
4. Retourne ta décision en JSON

## Format de Réponse:
{
  "next_agent": "nom_agent" ou "TERMINATE",
  "reasoning": "Pourquoi cet agent maintenant",
  "parameters": {
    "param1": "value1"
  }
}

## Règles de Décision:
- Toujours commencer par OCR si document non traité
- Guardrails AVANT tout traitement sensible
- RAG si besoin de contexte utilisateur
- Fraud detection si montant > 5000$ ou patterns suspects
- TERMINATE quand tu as assez d'info pour la décision finale
"""

ORCHESTRATOR_STATE_PROMPT = """## État Actuel du Claim:
Claim ID: {claim_id}
Type: {claim_type}
Montant: ${amount}
User ID: {user_id}

## Agents Déjà Exécutés:
{completed_agents}

## Données Collectées:
{collected_data}

## Question:
Quel est le PROCHAIN agent à appeler? Ou TERMINATE si prêt pour décision finale?
"""
```

### 2. Orchestrateur avec Boucle Intelligente

```python
async def intelligent_orchestrate_claim(
    claim_id: str,
    document_path: str,
    user_id: str,
    claim_type: str
) -> Dict[str, Any]:
    """
    Orchestrateur intelligent qui utilise un LLM pour décider
    dynamiquement quels agents appeler et dans quel ordre.
    """

    # État du traitement
    state = {
        "claim_id": claim_id,
        "claim_type": claim_type,
        "user_id": user_id,
        "document_path": document_path,
        "completed_agents": [],
        "collected_data": {},
        "processing_steps": []
    }

    # Registre des agents disponibles
    agents = {
        "ocr_agent": call_ocr_agent,
        "guardrails_agent": call_guardrails_agent,
        "rag_agent": call_rag_agent,
        "fraud_detection_agent": call_fraud_detection_agent,
        "policy_checker_agent": call_policy_checker_agent,
        "llm_decision_agent": call_llm_decision_agent
    }

    max_iterations = 10  # Protection contre boucles infinies
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # 1. Demander au LLM quel agent appeler ensuite
        next_action = await ask_llm_for_next_agent(state)

        # 2. Vérifier si terminé
        if next_action["next_agent"] == "TERMINATE":
            logger.info(f"Orchestration terminée: {next_action['reasoning']}")
            break

        agent_name = next_action["next_agent"]

        # 3. Vérifier que l'agent existe
        if agent_name not in agents:
            logger.error(f"Agent inconnu: {agent_name}")
            break

        # 4. Exécuter l'agent
        logger.info(f"Iteration {iteration}: Calling {agent_name}")
        logger.info(f"Reasoning: {next_action['reasoning']}")

        step_start = datetime.now()
        try:
            # Appeler l'agent avec les paramètres suggérés par le LLM
            agent_result = await agents[agent_name](
                state=state,
                parameters=next_action.get("parameters", {})
            )

            # 5. Mettre à jour l'état
            state["completed_agents"].append(agent_name)
            state["collected_data"][agent_name] = agent_result

            step_duration = int((datetime.now() - step_start).total_seconds() * 1000)
            state["processing_steps"].append({
                "agent": agent_name,
                "status": "completed",
                "duration_ms": step_duration,
                "output": agent_result,
                "llm_reasoning": next_action["reasoning"]
            })

        except Exception as e:
            logger.error(f"Agent {agent_name} failed: {str(e)}")
            state["processing_steps"].append({
                "agent": agent_name,
                "status": "failed",
                "error": str(e)
            })
            # Le LLM décidera quoi faire ensuite (retry, skip, terminate)

    return {
        "claim_id": claim_id,
        "status": "completed",
        "iterations": iteration,
        "processing_steps": state["processing_steps"],
        "final_data": state["collected_data"]
    }


async def ask_llm_for_next_agent(state: Dict) -> Dict[str, Any]:
    """
    Demande au LLM de décider quel agent appeler ensuite.
    """

    # Préparer le prompt avec l'état actuel
    completed_summary = "\n".join([
        f"- {agent}: ✓" for agent in state["completed_agents"]
    ]) or "Aucun agent exécuté encore"

    data_summary = json.dumps(
        {k: f"<{len(str(v))} chars>" for k, v in state["collected_data"].items()},
        indent=2
    )

    # Extraire le montant si disponible
    amount = "Unknown"
    if "ocr_agent" in state["collected_data"]:
        ocr_data = state["collected_data"]["ocr_agent"]
        amount = ocr_data.get("structured_data", {}).get("fields", {}).get("amount", {}).get("value", "Unknown")

    user_prompt = ORCHESTRATOR_STATE_PROMPT.format(
        claim_id=state["claim_id"],
        claim_type=state["claim_type"],
        amount=amount,
        user_id=state["user_id"],
        completed_agents=completed_summary,
        collected_data=data_summary
    )

    # Appeler le LLM
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            LLM_ENDPOINT,
            json={
                "model": LLM_MODEL_NAME,
                "messages": [
                    {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 500,
            }
        )

        if response.status_code == 200:
            result = response.json()
            generated_text = result["choices"][0]["message"]["content"]

            # Parser le JSON de la réponse
            try:
                # Extraire JSON si dans markdown
                if "```json" in generated_text:
                    json_start = generated_text.find("```json") + 7
                    json_end = generated_text.find("```", json_start)
                    generated_text = generated_text[json_start:json_end].strip()

                decision = json.loads(generated_text)
                return decision

            except json.JSONDecodeError:
                logger.error(f"Failed to parse LLM response: {generated_text}")
                # Fallback: terminer
                return {
                    "next_agent": "TERMINATE",
                    "reasoning": "Failed to parse LLM decision",
                    "parameters": {}
                }
        else:
            logger.error(f"LLM request failed: {response.status_code}")
            return {
                "next_agent": "TERMINATE",
                "reasoning": "LLM unavailable",
                "parameters": {}
            }
```

### 3. Implémentation des Agents (Wrapper Pattern)

```python
async def call_ocr_agent(state: Dict, parameters: Dict) -> Dict:
    """Wrapper pour l'agent OCR"""
    result = await call_mcp_server(
        OCR_SERVER_URL,
        "ocr_document",
        {
            "document_path": state["document_path"],
            "document_type": "claim_form",
            "language": "eng"
        }
    )
    return result


async def call_guardrails_agent(state: Dict, parameters: Dict) -> Dict:
    """Wrapper pour l'agent Guardrails"""
    ocr_data = state["collected_data"].get("ocr_agent", {})
    raw_text = ocr_data.get("raw_text", "")

    result = await call_mcp_server(
        GUARDRAILS_SERVER_URL,
        "check_sensitive_data",
        {
            "text": raw_text[:5000],
            "structured_data": ocr_data.get("structured_data", {})
        }
    )
    return result


async def call_rag_agent(state: Dict, parameters: Dict) -> Dict:
    """Wrapper pour l'agent RAG"""
    ocr_data = state["collected_data"].get("ocr_agent", {})
    claim_text = ocr_data.get("raw_text", "")

    # Récupérer user info
    user_info = await call_mcp_server(
        RAG_SERVER_URL,
        "retrieve_user_info",
        {
            "user_id": state["user_id"],
            "query": "active insurance contracts",
            "top_k": 5,
            "include_contracts": True
        }
    )

    # Récupérer similar claims
    similar_claims = await call_mcp_server(
        RAG_SERVER_URL,
        "retrieve_similar_claims",
        {
            "claim_text": claim_text[:1000],
            "top_k": 10,
            "min_similarity": 0.7
        }
    )

    return {
        "user_info": user_info,
        "similar_claims": similar_claims
    }


async def call_fraud_detection_agent(state: Dict, parameters: Dict) -> Dict:
    """Nouveau: Agent de détection de fraude"""
    ocr_data = state["collected_data"].get("ocr_agent", {})
    rag_data = state["collected_data"].get("rag_agent", {})

    # Logique de détection de fraude
    # (pourrait être un autre MCP server)
    fraud_score = 0.0
    suspicious_patterns = []

    # Exemple: vérifier montant vs historique
    amount_str = ocr_data.get("structured_data", {}).get("fields", {}).get("amount", {}).get("value", "0")
    try:
        amount = float(amount_str.replace("$", "").replace(",", ""))
        if amount > 10000:
            fraud_score += 0.3
            suspicious_patterns.append("High amount claim")
    except:
        pass

    # Vérifier fréquence des claims
    similar_claims = rag_data.get("similar_claims", [])
    if len(similar_claims) > 5:
        fraud_score += 0.2
        suspicious_patterns.append("Multiple recent claims")

    return {
        "fraud_score": fraud_score,
        "suspicious_patterns": suspicious_patterns,
        "requires_investigation": fraud_score > 0.5
    }


async def call_policy_checker_agent(state: Dict, parameters: Dict) -> Dict:
    """Nouveau: Vérification des polices d'assurance"""
    ocr_data = state["collected_data"].get("ocr_agent", {})
    rag_data = state["collected_data"].get("rag_agent", {})

    user_contracts = rag_data.get("user_info", {}).get("contracts", [])
    claim_type = state["claim_type"]

    # Vérifier si un contrat actif couvre ce type
    coverage_applies = False
    active_contracts = [c for c in user_contracts if c.get("is_active")]

    for contract in active_contracts:
        if contract.get("contract_type") == claim_type:
            coverage_applies = True
            break

    return {
        "coverage_applies": coverage_applies,
        "active_contracts_count": len(active_contracts),
        "policy_violations": [] if coverage_applies else ["No active coverage for claim type"]
    }


async def call_llm_decision_agent(state: Dict, parameters: Dict) -> Dict:
    """Agent de décision finale LLM"""
    # Utiliser la fonction make_final_decision existante
    # mais avec toutes les données collectées
    return await make_final_decision(
        claim_id=state["claim_id"],
        user_id=state["user_id"],
        ocr_results=state["collected_data"].get("ocr_agent", {}),
        rag_results=state["collected_data"].get("rag_agent", {}),
        user_contracts=state["collected_data"].get("rag_agent", {}).get("user_info", {}).get("contracts", [])
    )
```

---

## Avantages de l'Approche Intelligente

### 1. Adaptabilité
```python
# Claim simple (montant faible, utilisateur connu):
OCR → Guardrails → RAG → Decision
# 4 étapes

# Claim complexe (montant élevé, nouvel utilisateur):
OCR → Guardrails → RAG → Fraud Detection → Policy Checker → Decision
# 6 étapes

# Le LLM décide dynamiquement!
```

### 2. Gestion d'Erreurs Intelligente
```python
# Si OCR échoue partiellement:
LLM peut décider: "Appeler OCR avec paramètres différents"
# ou "Passer en manual_review directement"
```

### 3. Optimisation des Coûts
```python
# Claims AUTO simples: pas besoin de fraud detection
# Claims MEDICAL complexes: fraud detection + policy checker
# Le LLM optimise le parcours!
```

### 4. Traçabilité
```python
# Chaque étape a le reasoning du LLM:
{
  "agent": "fraud_detection_agent",
  "llm_reasoning": "Montant de $12,000 détecté, vérification fraude nécessaire",
  "status": "completed"
}
```

---

## Prompts Avancés pour l'Orchestrateur

### Prompt avec Few-Shot Examples

```python
ORCHESTRATOR_EXAMPLES = """
## Exemples de Décisions:

Exemple 1:
État: Claim AUTO, $500, OCR complété
Décision: {"next_agent": "rag_agent", "reasoning": "Besoin du contexte utilisateur pour vérifier couverture"}

Exemple 2:
État: Claim MEDICAL, $15,000, OCR + RAG complétés
Décision: {"next_agent": "fraud_detection_agent", "reasoning": "Montant élevé justifie vérification fraude"}

Exemple 3:
État: Claim HOME, $2,000, OCR + Guardrails + RAG complétés, user a contrat actif
Décision: {"next_agent": "llm_decision_agent", "reasoning": "Données suffisantes pour décision"}

Exemple 4:
État: Claim avec données sensibles détectées par Guardrails
Décision: {"next_agent": "TERMINATE", "reasoning": "Données sensibles non masquées, manual review requis"}
"""
```

---

## Métriques et Monitoring

```python
# Logger les décisions du LLM pour analyse
{
  "claim_id": "CLM-123",
  "orchestration_path": ["ocr", "guardrails", "rag", "fraud_detection", "decision"],
  "total_iterations": 5,
  "llm_decisions": [
    {"iteration": 1, "chose": "ocr", "reasoning": "..."},
    {"iteration": 2, "chose": "guardrails", "reasoning": "..."},
    ...
  ],
  "total_cost": "$0.042",  # Coût des appels LLM
  "processing_time_ms": 5420
}
```

---

## Migration Progressive

### Étape 1: Hybride (Code + LLM)
- Garder l'ordre fixe comme fallback
- LLM décide seulement les agents optionnels (fraud, policy check)

### Étape 2: LLM Planning
- LLM crée le plan complet au début
- Exécution séquentielle du plan

### Étape 3: Full Agent Loop (Recommandé)
- LLM décide à chaque itération
- Maximum de flexibilité

---

## Conclusion

Un orchestrateur intelligent combine:
1. **Code structuré**: Wrappers pour chaque agent
2. **LLM intelligent**: Décisions dynamiques basées sur contexte
3. **Prompts détaillés**: System prompt + exemples + état actuel
4. **Boucle de contrôle**: Itérations jusqu'à TERMINATE
5. **Traçabilité**: Logger chaque décision du LLM

C'est la base des systèmes agentic modernes comme AutoGPT, LangGraph, CrewAI.
