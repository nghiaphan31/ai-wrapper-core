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
* **Artifact** : Tout fichier produit ou utilisé : code, patch, doc, image, logs, bundles, etc. Chaque artefact doit être stocké et référencé (idéalement via hash et manifest).

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
* `ledger/` [NO GIT] : Journaux d'audit structurés (références croisées).
* `manifests/` [NO GIT] : Index locaux et hashes.

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

**6.4 Bundle de preuves**
Production d'un bundle (résumé, logs, diffs, erreurs) à chaque exécution locale pour feedback à l'IA.

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

**10.3 Intégrité**
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

**Séparation et non-persistance (REQ-AFI-003) — Distinct du Project Context :**
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
* Traçabilité : En cas de doute, l'utilisateur peut ouvrir le transcript.log pour prouver ce qu'il a demandé, et le comparer avec le fichier JSON brut de la réponse IA lié dans le ledger.
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
