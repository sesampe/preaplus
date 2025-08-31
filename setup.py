import os
import sys
import subprocess
import venv

REQUIRED_PYTHON = (3, 12)
VENV_DIR = "venv"
REQUIREMENTS_FILE = "requirements.txt"

def check_python_version():
    if sys.version_info < REQUIRED_PYTHON:
        sys.exit(f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ es requerido. Tú estás usando {sys.version_info.major}.{sys.version_info.minor}.")

def create_virtualenv():
    if not os.path.exists(VENV_DIR):
        print(f"🧪 Creando entorno virtual en ./{VENV_DIR}...")
        venv.create(VENV_DIR, with_pip=True)
    else:
        print("✅ Entorno virtual ya existe.")

def install_dependencies():
    pip_path = os.path.join(VENV_DIR, "bin", "pip") if os.name != 'nt' else os.path.join(VENV_DIR, "Scripts", "pip.exe")
    if not os.path.exists(REQUIREMENTS_FILE):
        sys.exit("❌ No se encontró requirements.txt")

    print("📦 Instalando dependencias...")
    subprocess.check_call([pip_path, "install", "-r", REQUIREMENTS_FILE])

def main():
    check_python_version()
    create_virtualenv()
    install_dependencies()
    print("🚀 Listo. Activa el entorno con:\n")
    print(f"  source {VENV_DIR}/bin/activate" if os.name != 'nt' else f"  {VENV_DIR}\\Scripts\\activate.bat")

if __name__ == "__main__":
    main()
