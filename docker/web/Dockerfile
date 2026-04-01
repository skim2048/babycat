# Babycat — Web Frontend Container (dev)
# Vue 3 + Vite dev server

FROM node:22-slim

WORKDIR /app
COPY debugging/package.json debugging/package-lock.json* ./
RUN npm install
COPY debugging/ .

EXPOSE 5173
CMD ["npm", "run", "dev"]
