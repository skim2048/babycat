# Babycat — Web Dashboard Container (dev)
# Vue 3 + Vite dev server

FROM node:22-slim

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
