FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* pnpm-lock.yaml* .npmrc* ./
RUN if [ -f pnpm-lock.yaml ]; then npm install -g pnpm && pnpm install --frozen-lockfile; else npm install; fi

COPY tsconfig.json eslint.config.mjs .prettierrc.json ./
COPY src ./src
COPY config ./config
COPY docs ./docs
COPY scripts ./scripts
COPY tools ./tools

RUN npm run build && npm prune --production

ENV NODE_ENV=production

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
