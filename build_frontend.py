#!/usr/bin/env python3
"""
Script para buildar o frontend React e copiar para a pasta static/dist
Execute este script antes de fazer deploy no Render.
"""
import subprocess
import shutil
import os
from pathlib import Path

# Diretórios
ROOT_DIR = Path(__file__).parent
FRONTEND_DIR = ROOT_DIR / "TindimDigest"
STATIC_DIR = ROOT_DIR / "static" / "dist"

def run_command(cmd: list, cwd: Path = None):
    """Executa um comando e mostra o output"""
    print(f"🔧 Executando: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, shell=True)
    if result.returncode != 0:
        print(f"❌ Erro ao executar: {' '.join(cmd)}")
        return False
    return True

def main():
    print("=" * 50)
    print("🚀 Build do Frontend Tindim")
    print("=" * 50)
    
    # 1. Verificar se a pasta do frontend existe
    if not FRONTEND_DIR.exists():
        print(f"❌ Pasta do frontend não encontrada: {FRONTEND_DIR}")
        return False
    
    # 2. Instalar dependências do frontend
    print("\n📦 Instalando dependências do frontend...")
    if not run_command(["npm", "install"], cwd=FRONTEND_DIR):
        return False
    
    # 3. Buildar o frontend
    print("\n🔨 Buildando o frontend...")
    if not run_command(["npm", "run", "build"], cwd=FRONTEND_DIR):
        return False
    
    # 4. Verificar se o build foi criado
    frontend_dist = FRONTEND_DIR / "dist"
    if not frontend_dist.exists():
        # Tenta dist/public (estrutura antiga do Vite)
        frontend_dist = FRONTEND_DIR / "dist" / "public"
    if not frontend_dist.exists():
        # Tenta client/dist
        frontend_dist = FRONTEND_DIR / "client" / "dist"
    
    if not frontend_dist.exists():
        print(f"❌ Pasta dist não encontrada após build")
        return False
    
    # 5. Limpar pasta de destino
    print(f"\n🗑️ Limpando pasta de destino: {STATIC_DIR}")
    if STATIC_DIR.exists():
        shutil.rmtree(STATIC_DIR)
    
    # 6. Copiar arquivos buildados
    print(f"\n📁 Copiando arquivos para: {STATIC_DIR}")
    shutil.copytree(frontend_dist, STATIC_DIR)
    
    # 7. Verificar resultado
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        print("\n✅ Build concluído com sucesso!")
        print(f"   Frontend disponível em: {STATIC_DIR}")
        
        # Listar arquivos
        print("\n📄 Arquivos gerados:")
        for item in STATIC_DIR.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(STATIC_DIR)
                size = item.stat().st_size / 1024
                print(f"   - {rel_path} ({size:.1f} KB)")
        
        return True
    else:
        print("❌ index.html não encontrado no build")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
