FROM node:20-alpine

# docker CLI is needed so the service can spawn isolated sandbox containers
# through the host Docker socket mounted by docker-compose.
RUN apk add --no-cache docker-cli

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src ./src
COPY public ./public

ENV PORT=8080
EXPOSE 8080
CMD ["node", "src/server.js"]
