# Documentation Implémentation : Core System
**Version :** 0.1.0 (Itération 1)
**Date :** 2026-01-28

## 1. Vue d'ensemble
Le noyau (Core) gère l'initialisation, la configuration et, surtout, la traçabilité des opérations. Il ne contient pas encore de logique IA.

## 2. Modules Principaux (`src/`)

### 2.1 Configuration (`config.py`)
* **Rôle :** Charge le fichier `project.json` depuis la racine.
* **Classe :** `ConfigLoader`
* **Instance Globale :** `GLOBAL_CONFIG`
* **Comportement :** Lève une erreur critique si le JSON est malformé ou absent.

### 2.2 Audit & Ledger (`audit.py`)
* **Rôle :** Journalisation structurée pour les machines (JSONL).
* **Fichier de sortie :** `ledger/events.jsonl` (Append-Only).
* **Champs clés :** `event_uuid`, `actor`, `action_type`, `artifacts_links`.
* **Instance Globale :** `GLOBAL_LEDGER`

### 2.3 Console & Transcript (`console.py`)
* **Rôle :** Interface Homme-Machine. Capture stdin/stdout.
* **Fichier de sortie :** `sessions/<YYYY-MM-DD>/transcript.log`.
* **Fonctionnement :** * Remplace `print()` par `GLOBAL_CONSOLE.print()` -> Écrit écran + log avec prefix `[WRAPPER]`.
    * Remplace `input()` par `GLOBAL_CONSOLE.input()` -> Capture saisie + log avec prefix `[USER]`.

### 2.4 Point d'Entrée (`main.py`)
* **Exécution :** `python3 -m src.main` (Requis pour la résolution des packages).
* **Rôle :** Orchestre le démarrage et la boucle d'interaction.

## 3. Structure des Données
Les sessions sont isolées par date. Le Ledger est global au projet.
