# Project Albert — Documentation d'Implémentation : Core System
**Version :** 0.1.0 (Itération 1)
**Date :** 2026-01-28

## 1. Vue d'ensemble
**Project Albert** est un outil local-first qui agit comme un *steward* (intendant) rigoureux entre l’Utilisateur et le Modèle IA.

Albert n’est pas un simple "chat" : il orchestre le workflow, écrit les artefacts sur disque (zéro copy-paste), et impose une **traçabilité vérifiable** (transcript + ledger + payloads bruts). Son rôle central est de garantir qu’à tout moment on puisse répondre, preuves à l’appui :
* **qui** a demandé **quoi**, **quand**,
* **quel** modèle a répondu,
* **quels** fichiers ont été produits/modifiés,
* et **où** retrouver l’échange brut correspondant.

Le noyau (Core) gère l'initialisation, la configuration et, surtout, la traçabilité des opérations. Il fournit également une boucle CLI interactive et les points d’entrée de workflow (`test_ai`, `implement`).

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

#### 2.4.1 Commandes interactives
Commandes disponibles dans la CLI interactive :
* `implement` : exécute une tâche d’implémentation via l’IA et écrit les fichiers dans `artifacts/<step_id>/`.
* `test_ai` : envoie une requête minimale à l’IA (sanity check de connectivité).
* `help` : affiche l’aide.
* `clear` : efface l’écran via `clear`.

> Note : `exit` / `quit` existent également pour quitter la CLI, mais ne font pas partie des commandes « cœur » du workflow.

#### 2.4.2 Nano Integration (multi-line input)
La commande `implement` supporte une saisie multi-ligne via **Nano Integration**.

* **Fonction :** `get_input_from_editor(prompt_text: str) -> str`
* **Principe :** au lieu d’un `input()` mono-ligne, le wrapper ouvre l’éditeur `nano` sur un fichier temporaire, puis relit le contenu complet du fichier à la fermeture.
* **Objectif :** permettre des prompts longs/multi-lignes de façon plus sûre (notamment pour le copy-paste de gros blocs), en réduisant les erreurs de terminal et les troncatures.
* **Flux :**
  1) création d’un fichier temporaire (`tempfile.NamedTemporaryFile(..., delete=False)`),
  2) ouverture de `nano` (`subprocess.run(["nano", tf_path], check=False)`),
  3) lecture du contenu du fichier,
  4) suppression du fichier temporaire.

> Prérequis : `nano` doit être disponible sur le système.

#### 2.4.3 Politique “Zero Waste” (annulation immédiate si entrée vide)
Le wrapper applique une politique **Zero Waste** sur `implement` :
* si l’instruction saisie est vide (ou uniquement des espaces), l’action est **annulée immédiatement**,
* le wrapper **ne construit pas** le contexte projet,
* le wrapper **n’appelle pas** l’API IA,
* aucun artefact n’est généré.

Cela évite de consommer des tokens et du temps sur des invocations accidentelles.

### 2.5 The 'albert' Launcher
Le projet fournit un script Bash portable `albert` à la racine du dépôt, conçu comme **launcher universel** pour exécuter la CLI sans dépendre du répertoire courant.

* **Portabilité & “symlink-proof” :** le script résout son propre chemin réel via `realpath`, ce qui garantit un comportement correct même si `albert` est appelé via un lien symbolique.
* **Résolution automatique de la racine :** à partir de ce chemin résolu, il déduit la racine du projet.
* **Auto-venv :** le launcher active automatiquement l’environnement virtuel `.venv` (si présent / attendu) avant de lancer la CLI.
* **Lancement standard :** exécute la CLI via `python -m src.main`.
* **Appel global possible :** si `albert` est lié dans le `PATH` (par exemple via un symlink vers `/usr/local/bin/albert`), la commande `albert` devient utilisable globalement, tout en pointant toujours vers la bonne racine projet.

## 3. Structure des Données
Les sessions sont isolées par date. Le Ledger est global au projet.
