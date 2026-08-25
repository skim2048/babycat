# @claude Babycat — reference web client, development server only (Vue 3 + Vite).
# @claude The client is outside the product scope (SRS §3.3); this container
# @claude exists to run it on the LAN without a local Node install. node_modules
# @claude is populated under the bind-mounted client/web directory.

FROM node:22.23.2-slim

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
