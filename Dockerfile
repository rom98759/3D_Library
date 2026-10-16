# syntax=docker/dockerfile:1

# --- Stage 1 : build du frontend React/Vite -------------------------------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2 : runtime Python / FastAPI -----------------------------------
FROM python:3.12-slim AS runtime

# Dépendances système minimales pour trimesh (chargement STL/3MF).
# Les miniatures (f3d + xvfb) ne sont PAS incluses ici : l'app dégrade
# proprement sans elles (pas de preview, aucun crash). Voir README § Docker.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY *.py ./
# Frontend déjà buildé par le stage précédent
COPY --from=frontend /app/frontend/dist ./frontend/dist

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV LIBRARY_DB_PATH=/data/library/library.db \
    INCOMING_DIR=/data/incoming \
    LIBRARY_DIR=/data/library

EXPOSE 8000
VOLUME ["/data"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "webapp:app", "--host", "0.0.0.0", "--port", "8000"]
