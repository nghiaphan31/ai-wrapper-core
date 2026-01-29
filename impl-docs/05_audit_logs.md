# Documentation Implémentation : Audit Logs
**Version :** 0.1.0
**Date :** 2026-01-29

## 1. Vue d'ensemble
Albert maintient deux flux de logs structurés en **JSONL** (un JSON par ligne, append-only) :

1) **Ledger événementiel** : `ledger/events.jsonl`
   * granularité fine (api_response, file_write, etc.)
   * référence vers payloads bruts (sessions/raw_exchanges)

2) **Audit Ledger transactionnel** : `audit_log.jsonl` (à la racine)
   * granularité « transaction » (ex: un `implement` réussi)
   * met l’accent sur les **tokens** et la **traçabilité des coûts**

## 2. Format JSONL : `audit_log.jsonl`
Chaque ligne est un objet JSON complet et valide.

### 2.1 Champs
* `transaction_uuid` (string, UUID) : identifiant unique de la transaction.
* `timestamp_utc` (string, ISO8601 UTC) : horodatage précis en UTC.
* `session_id` (string) : identifiant de session (actuellement: date `YYYY-MM-DD`).
* `step_id` (string) : identifiant de step (ex: `step_153012`).
* `user_instruction` (string) : instruction utilisateur (texte brut).
* `usage_stats` (object) :
  * `prompt_tokens` (int)
  * `completion_tokens` (int)
  * `total_tokens` (int)
* `status` (string) : statut de la transaction (ex: `success`).

### 2.2 Exemple
```json
{"transaction_uuid":"2f8a6d2d-6a7c-4ee0-a9db-8a8b2f3e0b1a","timestamp_utc":"2026-01-29T12:34:56.789012+00:00","session_id":"2026-01-29","step_id":"step_123456","user_instruction":"Add an audit ledger system...","usage_stats":{"prompt_tokens":1234,"completion_tokens":456,"total_tokens":1690},"status":"success"}
```

## 3. Notes d'intégrité
* Le fichier est **append-only** : pas de modification en place.
* Chaque entrée est écrite en **une seule ligne** pour faciliter :
  * grep/awk/jq,
  * ingestion dans des outils d’analyse,
  * reconstruction chronologique.

## 4. Lien avec les coûts
Le wrapper affiche une estimation de coût basée sur :
* $3.00 / 1M tokens d’entrée (`prompt_tokens`)
* $15.00 / 1M tokens de sortie (`completion_tokens`)

Cette estimation est un calcul local (non facturant) et sert de repère opérationnel.
