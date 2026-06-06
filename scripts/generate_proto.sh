#!/bin/bash
# Script para generar stubs de Python desde el archivo .proto

set -e

PROTO_FILE="core/proto/helios.proto"
OUTPUT_DIR="ai_engine/proto_generated"

echo "Generando stubs de Python desde ${PROTO_FILE}..."

python -m grpc_tools.protoc \
    -I core/proto \
    --python_out=${OUTPUT_DIR} \
    --grpc_python_out=${OUTPUT_DIR} \
    ${PROTO_FILE}

echo "✅ Stubs generados exitosamente en ${OUTPUT_DIR}"
ls -la ${OUTPUT_DIR}
