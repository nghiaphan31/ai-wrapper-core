# Documentation Implémentation : Core System
**Version :** 0.1.0 (Itération 1)
**Date :** 2026-01-28

## 1. Vue d'ensemble
Le noyau (Core) gère l'initialisation, la configuration et, surtout, la traçabilité des opérations. Il fournit également une boucle CLI interactive (commandes `help`, `clear`, `exit`) et les points d’entrée de workflow (`test_ai`, `gen_code`).

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
* **Fonctionnement :**
    * Remplace `print()` par `GLOBAL_CONSOLE.print()` -> Écrit écran + log avec prefix `[WRAPPER]`.
    * Remplace `input()` par `GLOBAL_CONSOLE.input()` -> Capture saisie + log avec prefix `[USER]`.

### 2.4 Point d'Entrée / CLI (`main.py`)
* **Exécution :** `python3 -m src.main` (requis pour la résolution des packages).
* **Rôle :** Orchestre le démarrage et la boucle d'interaction.
* **Boucle interactive :** attend une commande utilisateur et route vers les actions.
* **Commandes disponibles :**
  * `help` : affiche l’aide.
  * `clear` : efface l’écran via `clear`.
  * `exit` / `quit` : quitte la CLI.
  * `test_ai` : envoie une requête minimale à l’IA (sanity check de connectivité).
  * `gen_code` : génère/met à jour du code via l’IA et écrit les fichiers dans `artifacts/<step_id>/`.

#### 2.4.1 Nano Integration (multi-line input)
La commande `gen_code` supporte désormais une saisie multi-ligne via **Nano Integration**.

* **Fonction :** `get_input_from_editor(prompt_text: str) -> str`
* **Principe :** au lieu d’un `input()` mono-ligne, le wrapper ouvre l’éditeur `nano` sur un fichier temporaire, puis relit le contenu complet du fichier à la fermeture.
* **Objectif :** permettre des prompts longs/multi-lignes de façon plus sûre (notamment pour le copy-paste de gros blocs), en réduisant les erreurs de terminal et les troncatures.
* **Flux :**
  1) création d’un fichier temporaire (`tempfile.NamedTemporaryFile(..., delete=False)`),
  2) ouverture de `nano` (`subprocess.run(["nano", tf_path], check=False)`),
  3) lecture du contenu du fichier, 
  4) suppression du fichier temporaire.

> Note : cette intégration suppose que `nano` est disponible sur le système.

### 2.5 The Universal Launcher (ai script)
Le projet fournit un script Bash portable `ai` à la racine du dépôt, conçu comme **launcher universel** pour exécuter la CLI sans dépendre du répertoire courant.

* **Portabilité & “symlink-proof” :** le script résout son propre chemin réel via `realpath`, ce qui garantit un comportement correct même si `ai` est appelé via un lien symbolique.
* **Résolution automatique de la racine :** à partir de ce chemin résolu, il déduit la racine du projet, active automatiquement l’environnement virtuel `.venv`, puis lance la CLI via `src.main`.
* **Appel global possible :** si `ai` est lié dans le PATH (par exemple via un symlink vers `/usr/local/bin/ai`), la commande `ai` devient utilisable globalement, tout en pointant toujours vers la bonne racine projet.

## 3. Structure des Données
Les sessions sont isolées par date. Le Ledger est global au projet.
