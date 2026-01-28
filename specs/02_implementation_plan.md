# Spécification 02 : Plan d'Implémentation (Roadmap)
**Projet :** AI Wrapper Core
**Date :** 2026-01-28
**Phase :** A (Planification)

Ce document définit les étapes de développement pour transformer la baseline technique en outil fonctionnel.

## Itération 1 : Le Squelette (Core System & Logging)
**Objectif :** Mettre en place la structure Python, la gestion de configuration et, surtout, le système de traçabilité (Logs) qui est le cœur de la sécurité du wrapper.
* [ ] Mise en place du point d'entrée (`src/main.py` & `src/wrapper.py`).
* [ ] Chargement du `project.json`.
* [ ] Implémentation du Logger Double (Transcript + Ledger JSONL).
* [ ] Test : Lancer le wrapper, taper une commande factice, vérifier que tout est logué dans `sessions/` et `ledger/`.

## Itération 2 : Le Cerveau (API & Connectivité)
**Objectif :** Connecter le wrapper à l'API OpenAI (GPT-5.2) de manière sécurisée.
* [ ] Gestion des secrets (Chargement API Key hors Git).
* [ ] Client API : Envoi de requêtes simples.
* [ ] Gestion des erreurs API (Retry, Timeout).
* [ ] Test : Envoyer "Hello World" à l'IA et recevoir la réponse dans le terminal + logs bruts.

## Itération 3 : Les Mains (Artifacts & Zéro Copy-Paste)
**Objectif :** Implémenter la promesse clé "Zéro Copy-Paste". Le wrapper doit savoir écrire des fichiers.
* [ ] Définition du schéma JSON de réponse attendu de l'IA (Structure stricte).
* [ ] Module `ArtifactManager` : Parser le JSON, extraire le code, écrire dans `artifacts/`.
* [ ] Workflow de validation : L'utilisateur confirme avant déplacement vers `src/`.
* [ ] Test : Demander à l'IA de générer un script Python "Hello World", vérifier qu'il atterrit dans `artifacts/`.

## Itération 4 : La Mémoire (Context & Resume Packs)
**Objectif :** Gérer le contexte glissant et l'optimisation des tokens.
* [ ] Module `ContextManager` : Lire `specs/` et `src/` pour construire le prompt système.
* [ ] Création du "Resume Pack" : Compresser l'historique récent.
* [ ] Estimation des coûts (Token counting).
* [ ] Test : Faire une conversation à plusieurs tours sans exploser le contexte.

## Stratégie de Développement
Nous suivrons strictement l'ordre 1 -> 4.
Chaque itération doit se terminer par un commit sur `src/` et une mise à jour de `impl-docs/`.
