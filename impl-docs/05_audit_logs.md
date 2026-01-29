# Documentation Implémentation : Audit Logs
**Version :** 0.1.1
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

## 3. Input Capture & Echoing
### 3.1 Problème : l’« intent gap » avec un éditeur externe
Dans une CLI, la saisie standard via `input()` est naturellement capturée dans le transcript (stdin ↔ stdout). En revanche, une saisie réalisée dans un **éditeur externe** (ex: `nano`) ne traverse pas forcément le flux standard de la console : l’utilisateur peut écrire un prompt complet dans un fichier temporaire, puis le wrapper le relit.

Sans mesure spécifique, le transcript peut alors contenir :
* le prompt système “opening nano…”,
* puis les actions suivantes,

…mais **pas** le contenu réellement saisi dans Nano. Cela crée un trou de traçabilité : l’« Intent » dans le graphe de traçabilité peut devenir ambigu.

### 3.2 Règle implémentée (REQ_AUDIT_031)
Pour fermer ce gap, Albert **ré-injecte** explicitement le contenu capturé depuis l’éditeur externe dans le flux console/transcript **immédiatement après la lecture du fichier**.

* **Où :** `src/main.py` (fonction `get_input_from_editor`)
* **Quand :** juste après `content = f.read()`
* **Comment :** via `GLOBAL_CONSOLE.print(...)` afin que l’écho apparaisse à l’écran **et** dans `sessions/<YYYY-MM-DD>/transcript.log`.

### 3.3 Format stable dans le transcript
Le bloc est écrit avec un format volontairement simple et greppable :

```text
[USER_INPUT_ECHO]
> Content line 1
> Content line 2
[END_INPUT]
```

**Propriété clé :** en ouvrant `transcript.log`, on peut reconstruire l’historique exact de la session **sans deviner** ce qui a été tapé dans Nano.

### 3.4 Pourquoi (Traceability Graph)
Cette ré-injection garantit que le nœud **Intent** du Traceability Graph n’est jamais vide, même lorsque l’utilisateur utilise des outils externes.

## 4. Notes d'intégrité
* Le fichier est **append-only** : pas de modification en place.
* Chaque entrée est écrite en **une seule ligne** pour faciliter :
  * grep/awk/jq,
  * ingestion dans des outils d’analyse,
  * reconstruction chronologique.

## 5. Lien avec les coûts
Le wrapper affiche une estimation de coût basée sur :
* $3.00 / 1M tokens d’entrée (`prompt_tokens`)
* $15.00 / 1M tokens de sortie (`completion_tokens`)

Cette estimation est un calcul local (non facturant) et sert de repère opérationnel.
