# Babycat — Web Frontend Container (dev)
# Vue 3 + Vite dev server

FROM node:22-slim

WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ .

EXPOSE 5173
CMD ["npm", "run", "dev"]
