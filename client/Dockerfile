FROM node:10 AS build
WORKDIR /app
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
ENV VUE_APP_BASE_PATH=/coco-annotator/
RUN npm run build

FROM nginx:1.27-alpine AS production
COPY client/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/coco-annotator/
EXPOSE 80

FROM node:10 AS development

RUN npm install -g --quiet \
    @vue/cli@3.3.0 \
    @vue/cli-service@3.3.0

WORKDIR /workspace/

COPY ./client/package.json /workspace/package.json
RUN npm install
ENV NODE_PATH=/workspace/node_modules

WORKDIR /workspace/client/

EXPOSE 8080
CMD npm run serve