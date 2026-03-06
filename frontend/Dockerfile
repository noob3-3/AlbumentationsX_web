# ─────────────────────────────────────────────
# Stage: Build Vue3 + Vite frontend
# ─────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY package.json package-lock.json* ./

# Install dependencies (use ci if lockfile present)
RUN npm install --prefer-offline

# Copy source and build
COPY . .
RUN npm run build

# ─────────────────────────────────────────────
# Stage: Serve static files via nginx (standalone preview)
# This stage is optional — used only when running frontend independently.
# In production the FastAPI backend serves /dist directly.
# ─────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

COPY --from=builder /app/dist /usr/share/nginx/html

# SPA fallback: redirect all routes to index.html
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
