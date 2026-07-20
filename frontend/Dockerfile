FROM node:22-alpine AS dependencies
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM dependencies AS development
COPY . .
ENV NODE_ENV=development
CMD ["pnpm", "dev", "--hostname", "0.0.0.0"]

FROM node:22-alpine AS builder
WORKDIR /app
RUN corepack enable
ARG API_INTERNAL_URL=http://localhost:8000
ARG NEXT_PUBLIC_API_BASE=/api/v1
ENV API_INTERNAL_URL=$API_INTERNAL_URL
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
