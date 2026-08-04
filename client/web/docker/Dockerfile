# @claude Babycat — web dashboard container (dev).
# @claude Vue 3 + Vite dev server.
# @claude node_modules is populated under the bind-mounted project root (./node_modules).

FROM node:22-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

EXPOSE 5173
CMD ["sh", "-c", "npm install && npm run dev"]
