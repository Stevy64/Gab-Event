# Documentation Gab Event

| Fichier | Public | Contenu |
|---------|--------|---------|
| [../README.md](../README.md) | Développeurs | Vue d’ensemble, install locale, tests |
| [../DEPLOY_PYTHONANYWHERE.md](../DEPLOY_PYTHONANYWHERE.md) | Ops | Production actuelle (PythonAnywhere + Actions) |
| [DEPLOY_OVH.md](DEPLOY_OVH.md) | Ops | VPS OVH Cloud, Docker, HTTPS |
| [DEPLOY_MICROSERVICES.md](DEPLOY_MICROSERVICES.md) | DevOps | Architecture microservices + GitHub Actions |
| [guides/](guides/) | Formation | **Guides Word** (utilisateur, admin, installation) |

## Régénérer les guides Word

```bash
pip install -r requirements-docs.txt
python scripts/build_prod_guides.py
```

Les fichiers `.docx` sont écrits dans `docs/guides/`.
