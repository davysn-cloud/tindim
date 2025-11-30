#!/bin/bash
# Script de build para o Render
# Este script é executado automaticamente durante o deploy

echo "=== Build Tindim ==="

# 1. Instalar dependências Python
echo "📦 Instalando dependências Python..."
pip install -r requirements.txt

# 2. Verificar se Node.js está disponível
if command -v node &> /dev/null; then
    echo "📦 Node.js encontrado, buildando frontend..."
    
    # Entrar na pasta do frontend
    cd TindimDigest
    
    # Instalar dependências do frontend
    npm install
    
    # Buildar o frontend
    npm run build
    
    # Voltar para a raiz
    cd ..
    
    # Criar pasta static/dist se não existir
    mkdir -p static/dist
    
    # Copiar arquivos buildados
    if [ -d "TindimDigest/dist" ]; then
        cp -r TindimDigest/dist/* static/dist/
        echo "✅ Frontend copiado para static/dist"
    elif [ -d "TindimDigest/dist/public" ]; then
        cp -r TindimDigest/dist/public/* static/dist/
        echo "✅ Frontend copiado para static/dist"
    else
        echo "⚠️ Pasta dist não encontrada, frontend não será servido"
    fi
else
    echo "⚠️ Node.js não disponível, pulando build do frontend"
fi

echo "=== Build concluído ==="
