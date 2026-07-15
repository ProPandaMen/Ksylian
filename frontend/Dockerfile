FROM node:22-alpine AS build

WORKDIR /app
ARG VITE_APP_VERSION=0.1.0
ARG VITE_BUILD_SHA=local
ENV VITE_APP_VERSION=$VITE_APP_VERSION
ENV VITE_BUILD_SHA=$VITE_BUILD_SHA

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
