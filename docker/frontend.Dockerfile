FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --prefer-offline --no-audit --no-fund

COPY frontend/vite.config.js frontend/tsconfig.json ./
COPY frontend/src ./src
RUN npm run build

FROM nginx:stable-alpine-slim

COPY --link docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --link --from=build /app/dist/ /usr/share/nginx/html/

EXPOSE 80
