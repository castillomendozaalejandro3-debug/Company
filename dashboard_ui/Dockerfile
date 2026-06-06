FROM node:20-alpine AS builder

WORKDIR /app

# Copiar package files
COPY package*.json ./

# Instalar dependencias
RUN npm ci

# Copiar código fuente
COPY . .

# Construir para producción
RUN npm run build

# Imagen final minimalista
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

# Copiar build desde el builder
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./

EXPOSE 3000

ENV NODE_ENV=production

CMD ["npm", "run", "start"]
