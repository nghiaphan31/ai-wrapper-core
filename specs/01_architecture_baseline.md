# AI Wrapper — Spécification technique (baseline pré-code)

## 1) Objectif produit
Un wrapper local Linux (fonctionnant sur une machine unique : NUC ou Calypso) qui sert d’interface de travail avec une IA pour :
* produire/itérer du code (bash, python),
* gérer le cycle de vie dual de la documentation : spécifications techniques versionnées vs documentation d'implémentation continue,
* générer/manipuler des artefacts (fichiers, images, bundles),

 tout en garantissant : traçabilité, reproductibilité, maîtrise des coûts, sécurité d’exécution.

## 2) Contraintes & postulats (cadrage)
* Environnement : Linux, usage “local-first”.
* Interaction : orientée projets et sessions datées.
* Le wrapper doit pouvoir fonctionner dans un contexte “simple écran / confort limité terminal” : priorité à des sorties courtes, des résumés et des artefacts consultables plutôt que des interactions qui exigent de scroller énormément.
* La facturation et l’accès IA via API sont distincts des abonnements UI (ChatGPT Plus / Gemini Pro, etc.) → le wrapper doit être conçu pour un usage API.
* Garantie "Zéro Copy-Paste" : L'utilisateur ne doit JAMAIS avoir besoin de copier-coller du code depuis la sortie terminal vers un fichier. Le transfert du code généré vers le système de fichiers local doit être 100% automatisé par le wrapper pour garantir l'intégrité binaire (indentation, caractères spéciaux).

## 3) IA “tout-en-un” (intégration unique)
Le wrapper s’appuie sur OpenAI GPT-5.2 via l’API Responses comme moteur IA unique côté code.
Possibilité de :
* pinner un snapshot explicite (ex. gpt-5.2-2025-12-11),
* ou utiliser l’alias de modèle (ex. gpt-5.2) selon politique du projet.
Non-objectif (pré-code) : gérer plusieurs fournisseurs en même temps (même si des idées de “routing multi-modèles” existent ailleurs). Ici, on fige “une intégration IA”.

## 4) Modèle de données conceptuel

### Entités cœur
* **Project** : Identité stable (slug), description. Paramètres IA non secrets (modèle, styles, contraintes, budgets). Structure de documentation duale obligatoire (Spec vs Impl). Liens vers repo(s) éventuels.
* **Technical Specification (Cahier des charges)** : Document de référence versionné sous Git. Contenu : Objectifs, architecture, règles métier, contraintes. Évolution : Contrôlée et rigoureuse (commit/diff).
* **Implementation Documentation (Documentation technique)** : Document vivant, généré au fil de l’eau du développement. Contenu : Cartographie réelle de l'implémentation (fonctions, arborescence dossiers/fichiers, structure des logs, format des ledgers, localisation des artefacts). Rôle : Reflet de "ce qui est codé" à l'instant T.
* **Session** : Une session = une séquence de travail datée, rattachée à un projet. Doit produire des artefacts de “reprise” (resume pack) et un journal d’événements.
* **Step (micro-étape)** : Unité atomique de progression : une modification utile. Chaque step doit avoir : un prompt (intention), une réponse IA, des artefacts, une preuve (diff / logs / extraits), et une traçabilité vers l’état du code (conceptuellement, via Git, mais sans détailler l’exécution).
* **Ledger event (événement journalisé)** : Enregistrement append-only. Sert à l’audit : qui a demandé quoi, quelle IA, quels coûts, quels fichiers ont été produits, quelles commandes proposées, etc.
* **Artifact** : Tout fichier produit ou utilisé : code, patch, doc, image, logs, bundles zip, binaires.
  Chaque artefact doit être stocké et référencé (idéalement via hash et manifest).

## 5) Stockage local : organisation des dossiers & Stratégie Git
Le wrapper impose une arborescence de travail simple. Chaque élément a un statut Git défini (Tracked = versionné, Ignored = local uniquement).
Arborescence racine : `~/ai-work/projects/<project_slug>/`

* `project.json` [GIT] : Méta-données du projet, configuration non-secrète.
* `src/` [GIT] : Code source du projet (Python, Bash, etc.). C'est le "livrable" principal. Tout script validé ou code développé réside ici et suit un versioning rigoureux.
* `specs/` [GIT] : Cahier des charges techniques et évolutions fonctionnelles.
* `impl-docs/` [GIT] : Documentation technique vivante (auto-générée ou maintenue).
* `notes/` [GIT] : Mémoire contextuelle long-terme (summary.md, decisions.md, todo.md).
* `secrets/` [NO GIT] : API Keys, configurations spécifiques à la machine locale. Doit être dans .gitignore.
* `sessions/` [NO GIT] : Historique volumineux. Contient désormais pour chaque session :
    * `transcript.log` : Copie intégrale des E/S terminal (User <-> Wrapper).
    * `raw_exchanges/` : Fichiers JSON complets de chaque requête/réponse API (Wrapper <-> IA).
* `inputs/` [NO GIT] : Documents sources bruts copiés pour analyse.
* `outputs/` [NO GIT] : Fichiers générés intermédiaires.
* `artifacts/` [NO GIT] : Stockage "en vrac" des fichiers produits, bundles zip, binaires.
  * **Convention de nommage (Exigence de traçabilité) :** les dossiers d’artefacts **DOIVENT** suivre le pattern `step_YYYYMMDD_HHMMSS_<short_id>` afin de garantir la **triabilité chronologique** et la **traçabilité** (ex: `step_20260130_120500_a1b2`).
* `ledger/` [NO GIT] : Journaux d'audit structurés (références croisées).
* `manifests/` [NO GIT] : **Notary Ledger** local pour les artefacts non versionnés.
  * Rôle : servir de registre d’intégrité/traçabilité pour les fichiers **hors Git** (ex: `artifacts/`, `outputs/`, bundles, binaires), afin de pouvoir prouver **quels fichiers** ont été produits, **où** ils sont stockés, et **avec quelle empreinte cryptographique**.
  * Format : fichiers manifest structurés en **JSON** (machine-readable).
  * Nommage : les manifests DOIVENT utiliser un pattern unique, par exemple : `session_<uuid>_manifest.json` (ou un pattern similaire garantissant l’unicité).
  * Contexte d’archivage : ce dossier constitue le **pont** entre le workspace local et des systèmes d’archivage externes de type **Content Addressable Storage (CAS)**. Le manifest agit comme “preuve notariale” permettant de réconcilier un export/backup externe avec l’état local (fichiers non versionnés).

**Règles de Versioning :**
* Séparation stricte : Le code "source" du projet (dans src/) ainsi que la documentation (Specs + Impl) sont versionnés. Les données opérationnelles (Sessions + Logs + Artefacts) restent locales.
* Secrets : Exclusion formelle du dossier secrets/ via .gitignore.
* Flux de production : L'IA génère des propositions dans artifacts/ ou outputs/. Une fois validés par l'humain, les fichiers sont déplacés/mergés dans src/ et commités.
* Protection Git (Whitelisting) : Le fichier .gitignore à la racine doit impérativement utiliser une stratégie "Deny All / Allow Specific". Il doit ignorer tout (*) par défaut, et n'autoriser explicitement (avec !) que les dossiers versionnés (src/, specs/, impl-docs/, project.json, notes/) pour éviter toute pollution accidentelle par des logs ou des artefacts.

## 6) Workflow Séquentiel (Cycle de Vie)
Le travail est strictement divisé en deux phases distinctes.

**Phase A : Définition & Spécification**
* Objectif : Définir le "Quoi" et le "Pourquoi".
* Input : Idées brutes, contexte, objectifs.
* Action IA : Agit comme Architecte/Business Analyst.
* Output : Fichiers Markdown dans specs/.
* Interdit : Écrire du code dans src/ ou impl-docs/ durant cette phase.
* Livrable de fin de phase : Un commit Git validé sur le dossier specs/ (Baseline).

**Phase B : Implémentation & Itération**
* Objectif : Réaliser le "Comment".
* Input : La spécification validée (specs/) + Prompt d'implémentation.
* Action IA : Agit comme Développeur Senior.
* Boucle d'itération :
    * IA génère code + doc dans artifacts/.
    * Wrapper/Humain teste, debug, itère (sans polluer src/).
    * Validation (Definition of Done : Code + Doc synchros).
    * Output final : Commit Git sur src/ et impl-docs/.

**6.1 Entrées envoyées à l’IA (principe de réduction de tokens)**
Interdiction pratique : renvoyer “toute la conversation”.
Le wrapper construit un resume pack systématique (adapté à la phase en cours).

**6.2 Recherche locale avant appel IA (RAG “cheap”)**
Avant de payer des tokens, le wrapper doit privilégier la recherche texte locale et l'extraction ciblée.

**6.3 Sorties IA & Definition of Done**
* Mécanisme d'écriture (Anti Copy-Paste) : Le wrapper doit parser la réponse JSON de l'IA et écrire les fichiers directement sur le disque (artifacts/). L'utilisateur ne copie jamais de code manuellement.
* Gestion Différentielle : Mises à jour partielles (patches) pour les fichiers de contexte.
* Règle d'Or (Phase B) : Toute proposition de code (src/) DOIT être accompagnée de sa documentation technique (impl-docs/). Le wrapper signale tout manquement.

### 6.5 Gouvernance : The Trinity Protocol (REQ_CORE_060)
Le système applique un protocole de gouvernance visant à maintenir une **alignement strict** entre les trois couches :
1) **Specs** (`specs/`) — théorie / exigences,
2) **Code** (`src/`) — réalité / implémentation,
3) **Docs d’implémentation** (`impl-docs/`) — cartographie vivante de la réalité.

**Principe :** toute modification d’une couche DOIT déclencher une évaluation des deux autres.

* **Code Change (src/)** : nécessite une mise à jour correspondante dans `impl-docs/` et peut nécessiter un retrofit dans `specs/` si l’implémentation introduit un comportement non couvert.
* **Spec Change (specs/)** : nécessite une implémentation dans `src/` et une mise à jour dans `impl-docs/`.
* **Doc Change (impl-docs/)** : DOIT refléter le comportement réel du code et les exigences des specs (pas de “doc fictionnelle”).

Objectif : institutionnaliser une mentalité de **stewardship** (intendance) : la réalité (Code) et la théorie (Specs) se co-évoluent, et la documentation d’implémentation reste un miroir fidèle.

**Note de traçabilité :** toute évolution gouvernée par ce protocole DOIT être reflétée dans `traceability_matrix.md` (Source of Truth).

**6.4 Bundle de preuves**
Production d'un bundle (résumé, logs, diffs, erreurs) à chaque exécution locale pour feedback à l’IA.

## 7) Sécurité d’exécution (garde-fous)
Principe fondateur : le wrapper peut proposer des commandes/scripts, mais l’exécution réelle doit rester contrôlée.
Spécification conceptuelle des garde-fous :
un script/commande proposé(e) doit être :
* enregistré(e) dans les artefacts,
* accompagné(e) d’un contexte (“pourquoi”, “impact”),
* exécutable seulement après validation explicite,
* journalisé(e) dans le ledger.
journaliser aussi les refus (“non exécuté”) pour traçabilité.

## 8) Comptabilité tokens & coûts (fonction “vraie estimation”)
Le wrapper doit être capable d’estimer et suivre les coûts réels, pas “au feeling”.
Exigences :
* lire à chaque réponse API les champs d’usage (tokens entrée/sortie si disponibles),
* agréger par : session, projet, mois,
* appliquer une grille de prix du modèle utilisé (paramétrable),
* produire des rapports : “ce mois”, “ce projet”, “top sessions coûteuses”.
Optionnel : distinguer catégories (draft vs final, etc.) si le wrapper les encode.

## 9) Politique & configuration (YAML/JSON)
Chaque projet doit pouvoir définir une policy (concept) :
* modèle IA (snapshot/alias),
* budgets (caps par jour/mois/projet),
* limites de taille contexte,
* règles d’inclusion/exclusion d’extraits,
* règles de “diff-only” quand applicable,
* stratégie de reprise (resume pack obligatoire),
* règles de stockage/hachage (manifests on/off).

## 10) Journalisation Exhaustive & Auditabilité (Full Traceability)
Pour prévenir toute perte d'information ou hallucination non détectée, le logging est double et systématique.

**10.1 Niveau 1 : Transcript d'Interaction (Humain ↔ Wrapper)**
* Fichier : `sessions/<date>/transcript.log`
* Contenu : Copie verbatim de l'entrée standard (stdin) et sortie standard (stdout/stderr).
* Format : Texte brut horodaté. Capture exactement ce que l'utilisateur a écrit et ce que le wrapper a répondu à l'écran.

**10.2 Niveau 2 : Ledger Système (Wrapper ↔ IA)**
* Fichier : `ledger/events.jsonl`
* Format : JSONL structuré.
* Détail requis par événement :
    * timestamp_utc : Précision milliseconde.
    * event_uuid : Identifiant unique de l'événement.
    * actor : "user", "wrapper", ou "ai_model".
    * action_type : "api_request", "api_response", "file_write", "exec_command".
    * payload_ref : Lien vers le fichier brut stocké dans sessions/raw_exchanges/ (pour ne pas alourdir le ledger avec le contenu complet).
    * artifacts_links : Liste des chemins vers les fichiers créés ou modifiés (ex: artifacts/step_04/script.py).

### 10.3 Unified Traceability Model (The 6-W Framework)
Cette section formalise un **modèle unifié de traçabilité** : des sources de données distinctes (transcript, raw exchanges, artefacts, manifests, ledgers) forment un **graphe cohérent** permettant de répondre à des questions de type “Time Machine”, par exemple :

* *Qui* a demandé ce changement ?
* *Quand* a-t-il été demandé et appliqué ?
* *Quoi* exactement a été demandé, reçu, puis écrit sur disque ?
* *Où* se trouve la preuve (staging vs production) ?
* *Comment* relier un fichier final à l’échange IA et à sa preuve d’intégrité ?
* *Pourquoi* ce fichier a été écrit (instruction ↔ action) ?

Le principe directeur est le **Golden Thread** : chaque production (artifact) doit pouvoir être reliée sans ambiguïté à l’instruction utilisateur, à l’échange brut IA, aux écritures de fichiers, et à une preuve d’intégrité (hash), via des identifiants et des références croisées.

#### WHO (Qui)
* **Source principale :** transcript console (`src/console.py` → `sessions/<YYYY-MM-DD>/transcript.log`).
* **Source transactionnelle :** `audit_log.jsonl`.
* **Lien attendu :** **User ID** (ou identifiant opérateur) doit être transporté/associé à la transaction. À défaut, l’identité est prouvée par le transcript (contexte terminal) et l’environnement d’exécution.

#### WHEN (Quand)
* **Sessions datées :** `sessions/<YYYY-MM-DD>/...` (dossier de session) fournit le découpage temporel.
* **Horodatage ledger :** `ledger/events.jsonl` contient des `timestamp_utc` pour chaque événement.
* **Lien attendu :** la date de session + timestamps ledger permettent de reconstruire une chronologie robuste (sans dépendre des timestamps filesystem).

#### WHAT (Quoi)
* **Intent (instruction) :** `transcript.txt` / `transcript.log` contient la commande et l’instruction utilisateur.
* **Raw Data (échanges bruts IA) :** `sessions/.../raw_exchanges/` contient les payloads complets requête/réponse API.
* **Result (production) :** `artifacts/step_TIMESTAMP_ID/` contient les fichiers générés (staging).

#### WHERE (Où)
* **Staging (non versionné) :** `artifacts/` (propositions IA, preuves de génération, bundles).
* **Production (versionné) :** `src/` (livrable final, sous Git).

Ce découplage garantit que les sorties IA sont isolées tant qu’elles ne sont pas validées.

#### HOW (Comment relier les preuves)
Le graphe est reconstruit via trois liens structurants :

1) **Session ID** : relie Transcript ↔ Raw Exchanges
   * la session (souvent `YYYY-MM-DD`) scope les fichiers : `sessions/<session_id>/transcript.log` et `sessions/<session_id>/raw_exchanges/...`.

2) **Step ID** : relie Raw Exchange ↔ Artifact Folder
   * chaque exécution produit un dossier `artifacts/step_YYYYMMDD_HHMMSS_<short_id>/`.
   * le Step ID sert d’ancre pour associer une génération à un ensemble de fichiers.

3) **SHA-256** : relie Artifact ↔ Manifest ↔ Ledger
   * chaque fichier produit hors Git doit être haché en SHA-256 et inscrit dans un **manifest** (`manifests/`).
   * le manifest sert de preuve d’intégrité, réconciliable avec un export/backup externe.
   * le ledger (événementiel et/ou transactionnel) référence les chemins et permet de prouver l’existence d’une action d’écriture.

#### WHY (Pourquoi)
* **Source :** `ledger/events.jsonl`.
* **Lien attendu :** un événement `file_write` (action) doit pouvoir être relié au prompt/instruction (cause) via les identifiants de session/step et/ou une référence au payload brut.

Objectif : prouver que “ce fichier a été écrit **parce que** cette instruction a été donnée”, et non par une action implicite/non tracée.

**10.4 Intégrité**
* Les logs sont en mode "Append-Only".
* Le wrapper doit fournir un moyen simple de retrouver l'échange IA exact (le JSON brut envoyé et reçu) correspondant à une commande utilisateur donnée.

## 11) UX / Interface (pré-code)
Sans figer l’implémentation, l’expérience attendue :
* commande simple “appeler l’IA” sur une entrée structurée,
* possibilité de relancer avec resume pack,
* sorties concises + génération d’artefacts lisibles,
* mode “rapport” (coût, état projet, derniers steps).

### 11.1 Gestion du contexte : Project Context vs Transient Context
Le wrapper distingue formellement deux catégories de contexte injectées au modèle :

* **Project Context (persistant)** : contexte stable rattaché au projet (ex: specs/, impl-docs/, src/, notes/). Il est construit par le wrapper (resume pack) et sert de base de travail.
* **Transient Context (éphémère)** : contexte fourni “à la volée” par l’utilisateur pour une requête unique. Il ne modifie pas la mémoire long-terme du projet et n’est pas supposé être persisté dans les fichiers versionnés.

#### 11.1.1 Capacité : Ad-hoc File Ingestion (Exigence)
**But :** permettre à l’utilisateur de demander à l’IA d’analyser, débugger ou réécrire un document/log fourni au moment de l’appel, sans l’intégrer au Project Context persistant.

**Exigence (REQ-AFI-001) — Attachement explicite de fichiers locaux :**
* La CLI DOIT permettre à l’utilisateur d’attacher explicitement un ou plusieurs fichiers locaux à une requête (ex: via un ou plusieurs arguments de type chemin de fichier).

**Comportement système (REQ-AFI-002) — Lecture runtime et injection en Transient Context :**
* Le wrapper DOIT lire le contenu des fichiers attachés **au runtime** (au moment de l’exécution de la commande).
* Le contenu lu DOIT être injecté dans le prompt en tant que **Transient Context**, clairement séparé du Project Context.
* Le wrapper DOIT encapsuler chaque fichier ad-hoc avec des délimiteurs explicites incluant au minimum :
  * le chemin fourni (ou un identifiant),
  * le contenu brut,
  afin de permettre au modèle de distinguer les sources.

**Séparation et non-persistance (REQ-AFI-003) — Distinct du Project Context persistant :**
* Les fichiers ad-hoc NE DOIVENT PAS être intégrés automatiquement au Project Context (ex: ne pas les copier dans specs/, impl-docs/, src/ ou notes/ par défaut).
* Le wrapper DOIT traiter ces fichiers comme éphémères pour la requête courante.

**Cas d’usage (REQ-AFI-004) — Analyse / debug / réécriture on-the-fly :**
* Le mécanisme DOIT permettre à l’utilisateur de :
  * soumettre un log, un document, un fichier de configuration, un script isolé, etc.,
  * demander une analyse, un diagnostic, ou une réécriture ciblée,
  * sans nécessiter de copier-coller manuel dans le terminal.

> Note : La journalisation (transcript/ledger) reste applicable à l’opération (ex: mention des chemins attachés). Le traitement exact des contenus (stockage brut ou référence uniquement) est une décision d’implémentation ultérieure ; la baseline impose ici la capacité et la séparation conceptuelle Project vs Transient.

## 12) Critères d’acceptation (pré-code)
Le wrapper est conforme au baseline si, pour un projet donné :
* L'IA refuse d'écrire du code (src) si on est en phase de définition (specs).
* On peut créer une session, appeler l’IA, et retrouver : prompt, réponse brute, resume pack mis à jour, ledger événementiel.
* Traçabilité : En cas de doute, l'utilisateur peut ouvrir le transcript.log pour prouver ce qu'il a demandé et le comparer avec le fichier JSON brut de la réponse IA lié dans le ledger.
* Intégrité Code : Aucun copier-coller manuel n'est nécessaire. Le code présent dans artifacts/ est strictement identique au code reçu dans la réponse JSON de l'IA.
* La reprise d’une session ne nécessite pas de renvoyer tout l’historique.
* Les coûts/tokens sont visibles et agrégés.
* Les commandes/scripts proposés sont journalisés et ne s’exécutent pas “en douce”.
* Les artefacts produits sont stockés proprement et retrouvables.
* Le code développé (source) est clairement isolé dans un dossier src/ versionné.
* Le .gitignore est généré en mode strict (whitelist).
* Toute modification de code s'accompagne d'une mise à jour de la documentation d'implémentation.
* **Ad-hoc File Ingestion :** l’utilisateur peut attacher un ou plusieurs fichiers locaux à une requête ; le wrapper lit ces fichiers au runtime et injecte leur contenu comme **Transient Context**, distinct du Project Context persistant.

## 13) Analyse de Cohérence & Matrice de Couverture
Cette section évalue l'alignement entre les solutions techniques spécifiées et les objectifs initiaux. Elle doit être mise à jour à chaque révision des objectifs ou de l'architecture.

**13.1 Matrice Objectifs vs Solutions**
| Objectif (Sect. 1) | Solution Technique (Sect. 4, 5, 6, 7, 10) | État de Cohérence |
|---|---|---|
| Production Code (Bash/Python) | Isolation src/ (Git) vs artifacts/. Flux de validation humain. | Elevée. |
| Cycle de vie Projet | Workflow scindé en Phase A (Spec) et Phase B (Impl) + Diagrammes visuels. | Totale. |
| Documentation Duale | specs/ et impl-docs/ séparés. Règle "Definition of Done". | Elevée. |
| Confiance & Traçabilité (ANTI-DECEPTION) | Double logging (Transcript + Ledger avec payloads bruts). Tout est vérifiable. | Maximale. |
| Intégrité Scripts (Zéro Copy-Paste) | Écriture directe des artefacts via parsing JSON. Pas d'erreur humaine possible. | Totale. |
| Maîtrise des coûts | "Resume Packs" + Patchs différentiels. | Optimisée. |
| Sécurité d'exécution | Validation explicite. Isolation secrets. | Elevée. |
| Rigueur Versioning | Stratégie Git "Whitelisting". | Robustesse. |

**13.2 Gestion des Frictions Identifiées**
* Risque : Confusion phase design/code. -> Mitigation : Phases distinctes validées par Diagrammes (Sect 6).
* Risque : Désynchronisation Code/Doc. -> Mitigation : "Definition of Done".
* Risque : Erreurs de copié-collé. -> Mitigation : Automatisé par le wrapper (Sect 6.3).
* Risque : "Gaslighting" de l'IA. -> Mitigation : Full Traceability (Sect 10).

## 14) Table Synthétique des Exigences
Cette section formalise un **Requirements Registry** dérivé strictement du contenu des sections 1 à 13. Chaque ligne correspond à une exigence atomique, une contrainte opérationnelle, ou une fonctionnalité explicitement demandée.

**Convention d’ID :**
* `REQ_CORE_XXX` : workflow, intégration IA, sécurité d’exécution, “core loop”.
* `REQ_DATA_XXX` : modèle de données, stockage, Git, séparation des dossiers.
* `REQ_AUDIT_XXX` : journalisation, auditabilité, traçabilité, preuves.
* `REQ_UX_XXX` : ergonomie terminal, interaction, contexte, modes.

> Note de cohérence : Les exigences Ad-hoc File Ingestion sont déjà définies en prose sous la forme `REQ-AFI-00X` (Sect. 11.1.1). Dans le registre ci-dessous, elles sont reprises **à l’identique** et mappées à la convention globale via des IDs `REQ_UX_0XX` (sans supprimer les IDs existants).

> Note d’alignement (Audit “Ghost Features”) : L’audit a identifié des "Ghost Features" déjà présentes/attendues côté implémentation mais non formalisées dans la baseline. Elles sont désormais intégrées au registre comme exigences architecturales (sans détailler des aspects visuels comme les couleurs ANSI, ni des alias mineurs de commandes).

| Req_ID | Catégorie | Description de l'Exigence | Priorité |
|---|---|---|---|
| REQ_CORE_001 | CORE | Le wrapper DOIT fonctionner sur Linux en mode “local-first” sur une machine unique (NUC ou Calypso). | P0 |
| REQ_UX_001 | UX | L’interaction DOIT être orientée projets et sessions datées. | P0 |
| REQ_UX_002 | UX | Le wrapper DOIT privilégier des sorties courtes, des résumés et des artefacts consultables (contexte “simple écran / confort limité terminal”). | P0 |
| REQ_CORE_002 | CORE | Le wrapper DOIT être conçu pour un usage API (facturation et accès IA via API distincts des abonnements UI). | P0 |
| REQ_CORE_003 | CORE | Garantie “Zéro Copy-Paste” : l’utilisateur NE DOIT JAMAIS avoir besoin de copier-coller du code depuis la sortie terminal vers un fichier. | P0 |
| REQ_CORE_004 | CORE | Le transfert du code généré vers le système de fichiers local DOIT être 100% automatisé par le wrapper pour garantir l’intégrité binaire (indentation, caractères spéciaux). | P0 |
| REQ_CORE_005 | CORE | Le wrapper DOIT s’appuyer sur une intégration IA unique : OpenAI GPT-5.2 via l’API Responses comme moteur IA unique côté code. | P0 |
| REQ_CORE_006 | CORE | Le wrapper DOIT permettre de pinner un snapshot explicite de modèle (ex. `gpt-5.2-2025-12-11`) OU d’utiliser un alias de modèle selon la politique projet. | P1 |
| REQ_CORE_007 | CORE | Non-objectif : le wrapper NE DOIT PAS gérer plusieurs fournisseurs IA en même temps dans la baseline (intégration IA unique figée). | P2 |
| REQ_DATA_001 | DATA | Un **Project** DOIT avoir une identité stable (slug), une description et des paramètres IA non secrets (modèle, styles, contraintes, budgets). | P0 |
| REQ_DATA_002 | DATA | Un Project DOIT imposer une structure de documentation duale obligatoire : Spec vs Impl. | P0 |
| REQ_DATA_003 | DATA | La **Technical Specification** DOIT être un document de référence versionné sous Git ; son évolution DOIT être contrôlée et rigoureuse (commit/diff). | P0 |
| REQ_DATA_004 | DATA | L’**Implementation Documentation** DOIT être un document vivant reflétant “ce qui est codé” à l’instant T, incluant cartographie de l’implémentation (fonctions, arborescence, logs, ledgers, localisation artefacts). | P0 |
| REQ_DATA_005 | DATA | Une **Session** DOIT être datée, rattachée à un projet, et DOIT produire des artefacts de reprise (resume pack) et un journal d’événements. | P0 |
| REQ_DATA_006 | DATA | Un **Step** DOIT être une micro-étape atomique et DOIT contenir : prompt (intention), réponse IA, artefacts, preuve (diff/logs/extraits), et traçabilité vers l’état du code (conceptuellement via Git). | P0 |
| REQ_AUDIT_001 | AUDIT | Un **Ledger event** DOIT être append-only et servir à l’audit (qui a demandé quoi, quelle IA, quels coûts, quels fichiers produits, quelles commandes proposées, etc.). | P0 |
| REQ_DATA_007 | DATA | Un **Artifact** (tout fichier produit ou utilisé) DOIT être stocké et référencé (idéalement via hash et manifest). | P1 |
| REQ_DATA_008 | DATA | Le wrapper DOIT imposer une arborescence racine `~/ai-work/projects/<project_slug>/`. | P1 |
| REQ_DATA_009 | DATA | Les éléments versionnés DOIVENT inclure : `project.json`, `src/`, `specs/`, `impl-docs/`, `notes/`. | P0 |
| REQ_DATA_010 | DATA | Les éléments non versionnés DOIVENT inclure : `secrets/`, `sessions/`, `inputs/`, `outputs/`, `artifacts/`, `ledger/`, `manifests/`. | P0 |
| REQ_DATA_011 | DATA | Le dossier `secrets/` (API Keys, config machine) DOIT être exclu de Git via `.gitignore`. | P0 |
| REQ_AUDIT_002 | AUDIT | `sessions/` DOIT contenir par session : `transcript.log` (copie intégrale E/S terminal) et `raw_exchanges/` (JSON complets requête/réponse API). | P0 |
| REQ_DATA_012 | DATA | Règle de versioning : séparation stricte entre code+docs versionnés et données opérationnelles locales (sessions/logs/artefacts). | P0 |
| REQ_DATA_013 | DATA | Flux de production : l’IA génère des propositions dans `artifacts/` ou `outputs/` ; après validation humaine, les fichiers sont déplacés/mergés dans `src/` et commités. | P0 |
| REQ_DATA_014 | DATA | Protection Git : le `.gitignore` racine DOIT utiliser une stratégie “Deny All / Allow Specific” (ignorer `*` par défaut et autoriser explicitement uniquement les dossiers versionnés) pour éviter la pollution accidentelle par logs/artefacts. | P0 |
| REQ_CORE_008 | CORE | Le workflow DOIT être scindé strictement en deux phases : Phase A (Définition & Spécification) et Phase B (Implémentation & Itération). | P0 |
| REQ_CORE_009 | CORE | Phase A : l’IA agit comme Architecte/Business Analyst ; la sortie DOIT être des fichiers Markdown dans `specs/`. | P0 |
| REQ_CORE_010 | CORE | Phase A : il est INTERDIT d’écrire du code dans `src/` ou `impl-docs/`. | P0 |
| REQ_DATA_015 | DATA | Phase A : livrable de fin de phase = un commit Git validé sur `specs/` (Baseline). | P0 |
| REQ_CORE_011 | CORE | Phase B : l’IA agit comme Développeur Senior ; elle génère code + doc dans `artifacts/` ; le wrapper/humain teste/itère sans polluer `src/`. | P0 |
| REQ_DATA_016 | DATA | Phase B : output final = commit Git sur `src/` et `impl-docs/`. | P0 |
| REQ_CORE_012 | CORE | Réduction de tokens : le wrapper NE DOIT PAS renvoyer “toute la conversation” ; il DOIT construire un resume pack systématique adapté à la phase. | P0 |
| REQ_CORE_013 | CORE | Avant appel IA, le wrapper DOIT privilégier la recherche texte locale et l'extraction ciblée (RAG “cheap”) pour éviter de payer des tokens inutilement. | P1 |
| REQ_CORE_014 | CORE | Anti Copy-Paste : le wrapper DOIT parser la réponse JSON de l’IA et écrire les fichiers directement sur disque dans `artifacts/`. | P0 |
| REQ_CORE_015 | CORE | Gestion différentielle : le système DOIT supporter des mises à jour partielles (patches) pour les fichiers de contexte. | P1 |
| REQ_DATA_017 | DATA | Règle d’Or Phase B : toute proposition de code (`src/`) DOIT être accompagnée de la documentation technique correspondante (`impl-docs/`) ; le wrapper signale tout manquement. | P0 |
| REQ_CORE_060 | Core / Governance | **The Trinity Protocol :** toute modification d’une couche (Specs, Code, Docs) DOIT déclencher une évaluation des deux autres. Code change => update `impl-docs/` + retrofit potentiel `specs/`. Spec change => implémentation `src/` + update `impl-docs/`. Doc change => refléter le comportement réel du code et les exigences des specs. | P0 |
| REQ_AUDIT_003 | AUDIT | Un bundle de preuves (résumé, logs, diffs, erreurs) DOIT être produit à chaque exécution locale pour feedback à l’IA. | P1 |
| REQ_CORE_016 | CORE | Sécurité d’exécution : le wrapper peut proposer des commandes/scripts, mais l’exécution réelle DOIT rester contrôlée (validation explicite). | P0 |
| REQ_CORE_050 | Core / Security | **Safe Local Execution :** The system MUST possess a restricted interface to execute read-only system commands (e.g., directory listing, git status) to verify ground truth state. This interface MUST strictly block destructive commands (rm, mv, chmod, etc.) and sanitize inputs. | P0 |
| REQ_AUDIT_004 | AUDIT | Toute commande/script proposé(e) DOIT être enregistré(e) dans les artefacts. | P0 |
| REQ_UX_003 | UX | Toute commande/script proposé(e) DOIT être accompagné(e) d’un contexte (“pourquoi”, “impact”). | P1 |
| REQ_CORE_017 | CORE | Une commande/script proposé(e) DOIT être exécutable seulement après validation explicite. | P0 |
| REQ_AUDIT_005 | AUDIT | Une commande/script proposé(e) DOIT être journalisé(e) dans le ledger ; les refus (“non exécuté”) DOIVENT aussi être journalisés. | P0 |
| REQ_AUDIT_006 | AUDIT | Comptabilité coûts : le wrapper DOIT lire à chaque réponse API les champs d’usage (tokens entrée/sortie si disponibles). | P0 |
| REQ_AUDIT_007 | AUDIT | Le wrapper DOIT agréger les coûts/tokens par session, projet, mois. | P0 |
| REQ_CORE_018 | CORE | Le wrapper DOIT appliquer une grille de prix du modèle utilisé (paramétrable). | P0 |
| REQ_UX_004 | UX | Le wrapper DOIT produire des rapports : “ce mois”, “ce projet”, “top sessions coûteuses”. | P1 |
| REQ_AUDIT_008 | AUDIT | Optionnel : le wrapper PEUT distinguer des catégories (draft vs final, etc.) si encodées. | P2 |
| REQ_DATA_018 | DATA | Chaque projet DOIT pouvoir définir une policy (YAML/JSON concept) incluant : modèle (snapshot/alias), budgets (caps jour/mois/projet), limites de taille contexte, règles inclusion/exclusion extraits, règles “diff-only”, stratégie de reprise (resume pack obligatoire), règles stockage/hachage (manifests on/off). | P1 |
| REQ_AUDIT_009 | AUDIT | Journalisation : le logging DOIT être double et systématique (Transcript + Ledger). | P0 |
| REQ_AUDIT_010 | AUDIT | Transcript (Niveau 1) : fichier `sessions/<date>/transcript.log`, texte brut horodaté, copie verbatim stdin + stdout/stderr, capturant exactement ce que l’utilisateur a écrit et ce que le wrapper a affiché. | P0 |
| REQ_AUDIT_011 | AUDIT | Ledger (Niveau 2) : fichier `ledger/events.jsonl` en JSONL structuré. | P0 |
| REQ_AUDIT_012 | AUDIT | Chaque événement ledger DOIT inclure : `timestamp_utc` (précision milliseconde), `event_uuid`, `actor`, `action_type`, `payload_ref`, `artifacts_links`. | P0 |
| REQ_AUDIT_013 | AUDIT | `payload_ref` DOIT pointer vers le JSON brut dans `sessions/raw_exchanges/` pour éviter d’alourdir le ledger. | P0 |
| REQ_AUDIT_014 | AUDIT | Intégrité logs : les logs DOIVENT être en mode Append-Only. | P0 |
| REQ_AUDIT_015 | AUDIT | Le wrapper DOIT fournir un moyen simple de retrouver l’échange IA exact (JSON brut envoyé/reçu) correspondant à une commande utilisateur donnée. | P0 |
| REQ_AUDIT_030 | AUDIT | **Traceability Graph :** The system MUST ensure that every artifact produced can be traced back to the specific user prompt (Session/Step ID) and validated against its original integrity hash (Manifest) without gaps. | P0 |
| REQ_AUDIT_031 | Audit | **External Input Echo :** Any input captured via an external editor (e.g., Nano) MUST be explicitly echoed to the console transcript and audit logs immediately upon capture. This ensures the user's intent is recorded in the history. | P0 |
| REQ_UX_005 | UX | UX attendue : commande simple “appeler l’IA” sur une entrée structurée. | P1 |
| REQ_UX_006 | UX | UX attendue : possibilité de relancer avec resume pack. | P1 |
| REQ_UX_007 | UX | UX attendue : sorties concises + génération d’artefacts lisibles. | P0 |
| REQ_UX_008 | UX | UX attendue : mode “rapport” (coût, état projet, derniers steps). | P1 |
| REQ_UX_009 | UX | Le wrapper DOIT distinguer formellement Project Context (persistant) vs Transient Context (éphémère) injectés au modèle. | P0 |
| REQ_UX_010 | UX | Project Context : contexte stable rattaché au projet (ex: `specs/`, `impl-docs/`, `src/`, `notes/`), construit par le wrapper (resume pack), servant de base de travail. | P0 |
| REQ_UX_011 | UX | Transient Context : contexte fourni “à la volée” pour une requête unique, ne modifiant pas la mémoire long-terme et n’étant pas supposé être persisté dans les fichiers versionnés. | P0 |
| REQ_UX_012 | UX | (Reprise exacte REQ-AFI-001) La CLI DOIT permettre à l’utilisateur d’attacher explicitement un ou plusieurs fichiers locaux à une requête (arguments chemin de fichier). | P0 |
| REQ_UX_013 | UX | (Reprise exacte REQ-AFI-002) Le wrapper DOIT lire le contenu des fichiers attachés au runtime et l’injecter dans le prompt en tant que Transient Context, clairement séparé du Project Context, avec délimiteurs incluant au minimum chemin/identifiant + contenu brut. | P0 |
| REQ_UX_014 | UX | (Reprise exacte REQ-AFI-003) Les fichiers ad-hoc NE DOIVENT PAS être intégrés automatiquement au Project Context (pas de copie par défaut vers `specs/`, `impl-docs/`, `src/`, `notes/`) ; ils DOIVENT être traités comme éphémères. | P0 |
| REQ_UX_015 | UX | (Reprise exacte REQ-AFI-004) Le mécanisme DOIT permettre analyse/debug/réécriture on-the-fly de documents/logs/config/scripts sans copier-coller manuel dans le terminal. | P0 |
| REQ_CORE_019 | CORE | Critère d’acceptation : l’IA DOIT refuser d'écrire du code (`src`) si on est en phase de définition (`specs`). | P0 |
| REQ_AUDIT_016 | AUDIT | Critère d’acceptation : on DOIT pouvoir créer une session, appeler l’IA, et retrouver prompt, réponse brute, resume pack mis à jour, ledger événementiel. | P0 |
| REQ_AUDIT_017 | AUDIT | Critère d’acceptation : l’utilisateur DOIT pouvoir prouver via `transcript.log` ce qu’il a demandé et le comparer au JSON brut de la réponse IA lié dans le ledger. | P0 |
| REQ_CORE_020 | CORE | Critère d’acceptation : intégrité code “zéro copy-paste” — le code dans `artifacts/` DOIT être strictement identique au code reçu dans la réponse JSON de l'IA. | P0 |
| REQ_CORE_021 | CORE | Critère d’acceptation : la reprise d’une session NE DOIT PAS nécessiter de renvoyer tout l’historique. | P0 |
| REQ_AUDIT_018 | AUDIT | Critère d’acceptation : les coûts/tokens DOIVENT être visibles et agrégés. | P0 |
| REQ_AUDIT_019 | AUDIT | Critère d’acceptation : les commandes/scripts proposés DOIVENT être journalisés et NE DOIVENT PAS s’exécuter “en douce”. | P0 |
| REQ_DATA_019 | DATA | Critère d’acceptation : les artefacts produits DOIVENT être stockés proprement et retrouvables. | P0 |
| REQ_DATA_020 | DATA | Critère d’acceptation : le code développé (source) DOIT être isolé dans `src/` versionné. | P0 |
| REQ_DATA_021 | DATA | Critère d’acceptation : le `.gitignore` DOIT être généré en mode strict (whitelist). | P0 |
| REQ_DATA_022 | DATA | Critère d’acceptation : toute modification de code DOIT s’accompagner d’une mise à jour de la documentation d’implémentation. | P0 |
| REQ_UX_016 | UX | Critère d’acceptation : l’utilisateur DOIT pouvoir attacher un ou plusieurs fichiers locaux ; le wrapper DOIT les lire au runtime et injecte leur contenu comme Transient Context distinct du Project Context. | P0 |
| REQ_UX_017 | UX | **(Ghost Feature GF-002) Interactive Review :** le système DOIT présenter un unified diff et exiger une confirmation explicite **par fichier** avant d’appliquer des changements. | P0 |
| REQ_DATA_025 | DATA | **(Ghost Feature GF-001) Audit Ledger :** le système DOIT maintenir un ledger transactionnel au niveau opération (`audit_log.jsonl`) pour tracer coûts et statut des opérations, distinct du ledger événementiel. | P0 |
| REQ_UX_018 | UX | **(Ghost Feature GF-005) Editor Integration :** le système DOIT supporter la saisie multi-ligne via un éditeur externe (ex: Nano) pour des instructions complexes. | P1 |
| REQ_CORE_025 | CORE | **(Ghost Feature GF-007) Context Scoping :** le système DOIT permettre à l’utilisateur de sélectionner des scopes de contexte (ex: full, code, specs) afin d’optimiser l’usage des tokens. | P1 |
| REQ_DATA_026 | DATA | **(Ghost Feature GF-003) Auto-Git Workflow :** le système DOIT exécuter automatiquement une séquence atomique git commit/push **APRÈS** validation explicite des changements par l’utilisateur. | P0 |
| REQ_COST_005 | COST | **(Ghost Feature GF-006) Zero Waste Policy :** le système DOIT interrompre immédiatement le processus si l’instruction utilisateur est vide, afin d’éviter tout appel API et toute dépense de tokens inutile. | P0 |
| REQ_DATA_030 | Data Integrity | **Session Integrity Manifest :** At the conclusion of each session, the system MUST generate a structured manifest file (JSON) containing the list of all artifacts created, their storage paths, and their SHA-256 cryptographic hashes. This ensures integrity and traceability for non-versioned files. | High |

### 14.1 Vérification de cohérence (aucune exigence “hors-prose”)
Toutes les exigences listées ci-dessus sont des reformulations directes (ou reprises exactes) des sections 1 à 13.
* Les exigences explicitement demandées en “inclusions obligatoires” sont couvertes :
  * **Intégrité binaire / Zéro Copy-Paste** : REQ_CORE_003, REQ_CORE_004, REQ_CORE_014, REQ_CORE_020.
  * **Double logging (Transcript + Ledger JSONL)** : REQ_AUDIT_009 à REQ_AUDIT_015.
  * **Injection de fichiers Ad-hoc** : REQ_UX_012 à REQ_UX_015 (+ rappel REQ_UX_016).
  * **Gestion coûts & quotas** : coûts/tokens (REQ_AUDIT_006 à REQ_AUDIT_008, REQ_AUDIT_018) et budgets/caps via policy (REQ_DATA_018).
  * **Isolation secrets & stratégie Git** : REQ_DATA_011, REQ_DATA_014, REQ_DATA_021.
  * **Ghost Features (Audit) désormais formalisées** :
    * **Interactive Review (GF-002)** : REQ_UX_017.
    * **Audit Ledger transactionnel (GF-001)** : REQ_DATA_025.
    * **Editor Integration (GF-005)** : REQ_UX_018.
    * **Context Scoping (GF-007)** : REQ_CORE_025.
    * **Auto-Git Workflow (GF-003)** : REQ_DATA_026.
    * **Zero Waste Policy (GF-006)** : REQ_COST_005.

Si une exigence future devait être ajoutée au registre sans section détaillée correspondante, elle DOIT être soit :
1) supprimée du registre, soit
2) accompagnée d’une extension de prose dans la section appropriée avant d’être considérée “baseline”.
