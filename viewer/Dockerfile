FROM docker.io/library/node:20-alpine AS test
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY js ./js
COPY tests ./tests
RUN npm run test:coverage

FROM docker.io/library/nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
COPY js /usr/share/nginx/html/js
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
