# Spécification 10 — Autonomous Rebound Protocol (Chain of Thought & Action)
**Projet :** AI Wrapper Core (Albert)
**Date :** 2026-01-31
**Phase :** A (Spécification)

## 1) Objectif
Cette spécification formalise l’évolution du wrapper **d’un outil passif Request/Response** vers un **agent autonome** capable d’enchaîner des actions locales et des appels IA de manière **récursive**, jusqu’à obtention d’un résultat final.

**Ancien flux (passif) :**
`User → AI → Files → User`

**Nouveau flux (Rebound / autonome) :**
`User → AI → (Script Generation + Next Action Request) → Wrapper Executes Script → Wrapper Feeds Result back to AI → AI Analyzes → Final Response → User`

Cette boucle est appelée **Rebound Protocol**.

## 2) Définitions
- **AI Response JSON** : réponse structurée de l’IA au format JSON (protocole unifié) contenant au minimum `artifacts` et potentiellement d’autres champs.
- **Artifact** : fichier généré/écrit par le wrapper à partir de la réponse JSON (voir baseline REQ_CORE_014 / REQ_CORE_090).
- **next_action** : objet JSON optionnel décrivant une action que le wrapper doit exécuter automatiquement avant de rendre la main à l’utilisateur.
- **Rebound State** : état interne du wrapper indiquant qu’il doit exécuter `next_action` puis relancer l’IA avec un prompt de continuation.
- **Target Script** : script Python à exécuter localement, strictement situé sous `workbench/scripts/`.

## 3) Exigences

### REQ_AUTO_010 — The Rebound Protocol
**Exigence :**
L’IA **DOIT** pouvoir inclure un champ `next_action` dans sa réponse JSON, **séparé** de `artifacts`.

**Règles :**
1. La structure de réponse attendue devient (au minimum) :
   ```json
   {
     "thought_process": "...",
     "artifacts": [ ... ],
     "next_action": { ... }
   }
   ```
2. Si `next_action` est présent et valide, le wrapper **NE DOIT PAS** rendre le contrôle à l’utilisateur immédiatement.
3. En présence de `next_action`, le wrapper **DOIT** entrer en **Rebound State** et enchaîner l’exécution locale puis un nouvel appel IA (voir REQ_AUTO_030).

**Rationale :**
Permettre un agent autonome qui itère sur des preuves empiriques (outputs) plutôt qu’un simple générateur de fichiers.

**Critères d’acceptation :**
- Une réponse IA contenant `next_action` déclenche automatiquement une exécution locale contrôlée et un nouvel appel IA, sans intervention utilisateur intermédiaire.

---

### REQ_AUTO_020 — Next Action Structure
**Exigence :**
Le champ `next_action` **DOIT** respecter une structure JSON stricte.

**Schéma (v1) :**
```json
{
  "type": "exec_and_chain",
  "target_script": "workbench/scripts/...",
  "continuation_prompt": "Context for the next step..."
}
```

**Contraintes :**
- `type` :
  - **OBLIGATOIRE**
  - valeur autorisée (v1) : `"exec_and_chain"`
- `target_script` :
  - **OBLIGATOIRE**
  - chemin **relatif à la racine projet**
  - doit pointer **strictement** sous `workbench/scripts/` (voir REQ_AUTO_040)
- `continuation_prompt` :
  - **OBLIGATOIRE**
  - texte injecté dans le prompt suivant pour guider l’analyse post-exécution

**Règles d’évolution :**
- Toute extension de `type` (ajout de nouveaux types de next_action) doit être spécifiée dans une révision ultérieure (v2) avant implémentation.

---

### REQ_AUTO_030 — State Machine Loop (Rebound State)
**Exigence :**
La boucle principale (`main.py`) **DOIT** gérer un état **Rebound State** permettant l’enchaînement automatique :

**Logique obligatoire (v1) :**
1. Réception d’une réponse IA contenant `next_action`.
2. Passage en **Rebound State**.
3. Exécution du `target_script`.
4. Capture de la sortie d’exécution :
   - **STDOUT** (obligatoire)
   - **STDERR** (recommandé; si disponible, doit être capturé et journalisé)
   - code de retour (return code)
5. Construction d’un **nouveau System Prompt / User Prompt** pour l’appel IA suivant :
   - concaténation de :
     - `continuation_prompt`
     - un bloc contenant le STDOUT (et idéalement STDERR + return code)
6. Appel IA suivant.
7. Répétition tant que `next_action` est présent.
8. Sortie de la boucle et retour utilisateur uniquement lorsque la réponse IA **ne contient plus** de `next_action` (ou en cas d’erreur bloquante).

**Invariants :**
- Le wrapper doit préserver l’approche **Artifact-First** : si l’IA demande l’exécution d’un script, le script doit exister sur disque (généré au préalable via `artifacts`) avant exécution.
- Le wrapper doit rester compatible avec les exigences de sécurité d’exécution existantes (notamment REQ_CORE_055) et les renforcer via REQ_AUTO_040.

**Gestion d’erreur (v1) :**
- Si l’exécution échoue (script introuvable, violation sandbox, exception, timeout), le wrapper :
  1) journalise l’échec (voir REQ_AUTO_050),
  2) fournit à l’IA un bloc de continuation contenant le diagnostic (erreur + stderr + return code),
  3) relance l’IA pour permettre correction/diagnostic, **sauf** si une politique de sécurité stoppe l’exécution.

---

### REQ_AUTO_040 — Security & Sandbox (Next Action Execution)
**Exigence :**
L’exécution automatique demandée via `next_action` **DOIT** être strictement sandboxée.

**Règles de sécurité :**
1. **Restriction de chemin absolue :**
   - `next_action.target_script` est **STRICTEMENT limité** à la hiérarchie `workbench/scripts/`.
   - Toute tentative de ciblage hors de ce dossier (ex: `src/`, `/tmp`, `../`, chemin absolu) est **FORBIDDEN**.
2. **Interdiction d’auto-exécuter du code produit/livrable :**
   - Toute tentative d’auto-exécuter un script dans `src/` est **interdite**.
3. **Interdiction de commandes système arbitraires :**
   - `next_action` ne doit pas permettre l’exécution de commandes shell.
   - L’unique action autorisée (v1) est l’exécution d’un **script Python** sous `workbench/scripts/` via un runner sandboxé.
4. **No shell execution :**
   - l’exécution doit être réalisée sans `shell=True`.
5. **Timeout obligatoire :**
   - l’exécution doit être bornée (timeout) pour éviter les boucles infinies ou blocages.

**Rationale :**
Empêcher l’agent autonome de devenir un vecteur d’exécution arbitraire ou d’auto-modification incontrôlée du livrable.

---

### REQ_AUTO_050 — Traceability (Ledger-first, Final Result to User)
**Exigence :**
Tous les pas intermédiaires de la boucle Rebound **DOIVENT** être journalisés dans `ledger/`, tandis que l’interface utilisateur doit mettre en avant **uniquement le résultat final**.

**Règles :**
1. **Journalisation obligatoire des étapes intermédiaires :**
   - sortie script (stdout/stderr),
   - erreurs/diagnostics,
   - réponses IA intermédiaires (y compris `thought_process` si présent),
   - références aux raw exchanges (payload_ref) lorsque disponibles.
2. **Affichage utilisateur :**
   - la console peut afficher des informations de progression, mais la sortie principale doit être structurée pour que le **Final Result** soit clairement distingué.
3. **Principe d’auditabilité :**
   - un auditeur doit pouvoir reconstruire la chaîne complète :
     `User instruction → AI response → artifacts → next_action → exec output → continuation prompt → AI response → ... → final response`.

**Critères d’acceptation :**
- Après une exécution Rebound, les fichiers dans `ledger/` permettent de relier chaque exécution locale et chaque appel IA à un Step/Session.
- L’utilisateur obtient une réponse finale lisible sans être noyé par les sorties intermédiaires.

## 4) Impacts & Alignement avec les exigences existantes
- **REQ_CORE_090 (Unified Generation Protocol)** : la génération de scripts reste via JSON `artifacts`.
- **REQ_CORE_055 (Workbench Execution Sandbox)** : le runner existant constitue la base de la sandbox; REQ_AUTO_040 renforce la restriction dans le contexte d’auto-exécution.
- **REQ_AUDIT_060 (Transparent Tool Chain)** : la chaîne doit rester vérifiable (script + output traçables).
- **REQ_CORE_095 (Explicit Execution Request)** : cette exigence décrit la séparation génération/exécution dans un workflow humain; le Rebound Protocol introduit une exécution automatique conditionnée par `next_action`, qui doit être considérée comme un **nouveau mode** explicitement spécifié ici et strictement sandboxé.

## 5) Non-objectifs (v1)
- Multi-actions (plusieurs `next_action` dans une seule réponse).
- Planification complexe (workflows DAG), scheduling, ou exécution parallèle.
- Exécution de commandes shell arbitraires.
- Auto-modification directe de `src/` via exécution (interdit).

## 6) Notes de gouvernance (Trinity Protocol)
Toute implémentation de cette spécification devra :
- mettre à jour **le code** (`src/`),
- mettre à jour la **documentation d’implémentation** (`impl-docs/`),
- mettre à jour la **matrice de traçabilité** (`traceability_matrix.md`) avec :
  - REQ_AUTO_010, REQ_AUTO_020, REQ_AUTO_030, REQ_AUTO_040, REQ_AUTO_050,
  - les modules concernés,
  - et le statut (Planned/Partial/Implemented).

> IMPORTANT : Cette spécification introduit de nouveaux Req_ID. Avant toute implémentation, le registre et la matrice de traçabilité doivent être étendus pour inclure ces exigences.
