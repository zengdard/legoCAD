# legoCAD — génération de sets LEGO constructibles
#
# Le pipeline volume -> briques -> notice ne dépend que de la bibliothèque
# standard (plus Pillow pour les images). LeoCAD et la bibliothèque LDraw
# sont optionnels : sans eux, le serveur utilise le rendu SVG isométrique.
#
#   docker build -t legocad .
#   docker run -p 8000:8000 -e DEEPSEEK_API_KEY=sk-... legocad
#
# La bibliothèque LDraw (~615 Mo) n'est pas incluse dans l'image : monte-la
# si tu veux importer des modèles LDraw arbitraires ou utiliser LeoCAD.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LEGOCAD_NO_RENDER=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir "Pillow>=10" "openai>=1.30"

COPY . .
RUN mkdir -p out/web models

EXPOSE 8000
CMD ["python3", "web/server.py", "--host", "0.0.0.0", "--port", "8000"]
