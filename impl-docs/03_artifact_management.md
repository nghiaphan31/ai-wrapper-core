# Documentation Implémentation : Artifact Management
**Version :** 0.1.0 (Itération 3)
**Date :** 2026-01-28

## 1. Vue d'ensemble
Ce module implémente le principe "Zéro Copy-Paste". Il transforme les réponses JSON structurées de l'IA en fichiers physiques sur le disque local.

## 2. Protocole d'Échange (JSON Protocol)
L'IA ne doit plus répondre en texte libre pour la génération de code. Elle doit suivre ce schéma strict :
```json
{
  "thought_process": "Explication...",
  "artifacts": [
    {
      "path": "src/mon_script.py",
      "operation": "create",
      "content": "print('code')"
    }
  ]
}
```

## 4. Workflow Utilisateur
1. **Commande `implement`** : l’utilisateur décrit la tâche (multi-ligne possible via Nano Integration).
