# 1) FRONT build
FROM node:20-alpine AS front
WORKDIR /frontend
ARG VITE_API_BASE=https://api.communipay.ru
ENV VITE_API_BASE=$VITE_API_BASE
COPY frontend/ ./
RUN npm ci && npm run build --no-cache
RUN ls -la dist && ls -la dist/assets

# 2) APP image
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y nginx supervisor && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Python deps
COPY requirements.txt /app/
RUN python -m venv /venv && /venv/bin/pip install -U pip && /venv/bin/pip install -r requirements.txt
# Project
COPY . /app
# Nginx / Supervisor
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
# Front static
COPY --from=front /frontend/dist/ /usr/share/nginx/html/
RUN mkdir -p /app/templates /app/staticfiles && \
    true

COPY --from=front /frontend/dist/index.html /app/templates/index.html
COPY --from=front /frontend/dist/assets /app/staticfiles/assets
COPY --from=front /frontend/dist/assets /app/static/assets

RUN mkdir -p /app/staticfiles

# при старте контейнера прогоняем collectstatic (админка и т.п.)
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
# Port for Fly
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
