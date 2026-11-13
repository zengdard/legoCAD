# legoCAD — serveur web

Interface et API pour générer un set constructible depuis un navigateur.

```bash
python3 web/server.py --host 127.0.0.1 --port 8000
```

Puis <http://127.0.0.1:8000>.

## Fonctionnalités

- **Formes** prêtes à l'emploi (maison, fusée, voiture, canard, sapin,
  brique géante) — aucun LLM, aucun réseau.
- **Texte → volume** : avec `DEEPSEEK_API_KEY` (ou `OPENAI_API_KEY`), le LLM
  écrit un programme de volume (structure-as-code), exécuté dans un
  sous-processus borné. Sans clé, un classifieur de mots-clés choisit une
  forme proche.
- **Import** : `.ldr/.mpd` (voxelisé puis recompilé) ou image (mosaïque aux
  couleurs LDraw réelles).
- **Livrables** : `.ldr`, notice HTML imprimable, BOM CSV/JSON, wanted list
  BrickLink, aperçu 3D (SVG ou LeoCAD).

## API

| Route | Méthode | Corps |
|---|---|---|
| `/api/health` | GET | — |
| `/api/examples` | GET | — |
| `/api/generate` | POST | `{"shape":"house","name":"maison","width":16,"video":false}` ou `{"prompt":"une fusée rouge","name":"fusee"}` |
| `/api/import` | POST | `{"name":"x","filename":"m.ldr","data":"<base64>","video":false}` |

Réponse : `{ok, job, score, bricks, bom, files:{ldr,preview,notice,csv,xml,json}, source}`.
Les fichiers sont servis sous `/out/web/<job>/`.

Limites : 64 Ko pour `/api/generate`, 4 Mo pour `/api/import` (3 Mo
décodés) ; une génération à la fois (verrou). Un volume > 60 000 voxels ou
> 96 studs de côté est refusé.

## Déploiement

### Docker

```bash
docker compose up --build
# http://127.0.0.1:8000
```

`LEGOCAD_NO_RENDER=1` (par défaut dans le conteneur) désactive LeoCAD : le
rendu SVG isométrique est utilisé, sans Flatpak ni bibliothèque LDraw.

### VPS + Cloudflare Tunnel

```bash
# sur le VPS
git clone https://github.com/zengdard/legoCAD && cd legoCAD
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-...
setsid nohup python3 web/server.py --host 127.0.0.1 --port 8000 \
  >/tmp/legocad.log 2>&1 &

# sur la machine locale (ou sur le VPS)
cloudflared tunnel --url http://127.0.0.1:8000
```

Mettre un reverse proxy (Caddy/Traefik) devant si le service doit rester
public : le serveur n'a ni authentification ni limitation de débit.

### Notes

- LeoCAD (Flatpak) n'est pas nécessaire en ligne ; pour l'activer, installer
  LeoCAD dans l'image et monter `ldraw/` (615 Mo).
- Les jobs sont écrits dans `out/web/<job>/` ; prévoir un `cron` de nettoyage
  ou un volume dédié.
- Le mode texte coûte des tokens : limiter `max_tokens`, journaliser les
  erreurs, et garder le repli heuristique si l'API est indisponible.
