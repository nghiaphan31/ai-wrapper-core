# Documentation Implémentation : AI Connectivity
**Version :** 0.1.0 (Itération 2)
**Date :** 2026-01-28

## 1. Vue d'ensemble
Ce module gère l'interaction sécurisée avec l'API OpenAI. Il isole la gestion des secrets et garantit que chaque octet échangé avec l'IA est archivé pour audit.

## 2. Module Client (`src/ai_client.py`)

### 2.1 Gestion de la Sécurité
* **Stockage Clé :** Fichier `secrets/openai_key` (Exclu du Git).
* **Chargement :** Lecture à l'initialisation de la classe `AIClient`.
* **Règle :** Crash immédiat si la clé est absente ou malformée (`sk-...`).

### 2.2 Mécanisme d'Appel (`send_chat_request`)
1.  **Construction :** Prépare les messages (System + User).
2.  **Appel API :** Utilise le client officiel `openai` (synchronous).
3.  **Archivage Brut (Raw Exchange) :**
    * Crée un fichier JSON unique par requête dans `sessions/raw_exchanges/<uuid>.json`.
    * Contient : Timestamp, Modèle, Input complet, Output complet (metadata incluses).
4.  **Journalisation Ledger :**
    * Enregistre un événement `api_response` dans `ledger/events.jsonl`.
    * Inclut une référence (`payload_ref`) vers le fichier JSON brut.

## 3. Configuration
* **Modèle :** Défini dans `project.json` sous `policy.model_alias` (défaut: gpt-4o ou gpt-5.2 selon disponibilité).
