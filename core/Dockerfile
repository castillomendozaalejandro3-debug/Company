FROM rust:1.75-slim as builder

WORKDIR /app

# Instalar dependencias para protobuf
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de configuración
COPY Cargo.toml build.rs ./
COPY proto/ ./proto/

# Crear estructura de directorios src
RUN mkdir -p src

# Copiar código fuente
COPY src/ ./src/

# Compilar en modo release
RUN cargo build --release

# Imagen final minimalista
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar binario compilado
COPY --from=builder /app/target/release/helios_core .

EXPOSE 50051

CMD ["./helios_core"]
