FROM node:22-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm ci
COPY . .
# On Railway (or similar), set this service's VITE_API_BASE variable to the backend's
# public URL (e.g. https://smt6-backend-production.up.railway.app, no trailing slash).
# Leave unset for the bundled nginx proxy (local Docker Compose) to keep working as before.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
