# syntax=docker/dockerfile:1

FROM node:20-alpine AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1


FROM base AS dev

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]


FROM base AS build

COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build


FROM base AS prod

ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

# Unprivileged: the node image already ships a `node` user.
USER node
EXPOSE 3000
CMD ["node", "server.js"]
