@echo off
rem Instala el soporte de voces de personaje (RVC). Descarga ~3 GB (PyTorch con CUDA).
cd /d "%~dp0.."
.venv\Scripts\python.exe -m pip install "pip>=24" "setuptools<=80.6.0"
.venv\Scripts\python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
.venv\Scripts\python.exe -m pip install infer_rvc_python
.venv\Scripts\python.exe -m pip install "numpy==1.26.4"
.venv\Scripts\python.exe -c "import torch; print('CUDA disponible:', torch.cuda.is_available())"
pause
