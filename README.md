Scraper Web V2

Instrucciones para construir el ejecutable (Windows - PowerShell)

Requisitos previos
- Python 3.10+ (se recomienda 3.11)
- pip
- Visual C++ Build Tools (para algunas wheels) opcional

1) Crear y activar entorno virtual (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2) Instalar dependencias:

```powershell
pip install -r requirements.txt
# Playwright necesita instalación adicional de navegadores
pip install playwright
python -m playwright install
```

3) Construir ejecutable con PyInstaller usando el spec proporcionado:

```powershell
pip install pyinstaller
pyinstaller ScraperWEB.spec
```

Notas y recomendaciones
- He actualizado el nombre del ejecutable en `ScraperWEB.spec` a "Scraper Web V2".
- Playwright no siempre empaca bien con PyInstaller; la recomendación es instalar Playwright en el sistema/venv y ejecutar `python -m playwright install` en la máquina de destino después de desplegar.
- Si necesitas un ejecutable "sin consola" (GUI-only), cambia `console=True` por `console=False` en el spec.
- Si quieres un icono, añade la opción `icon='ruta\a\icono.ico'` en la llamada a `EXE` del spec.

Problemas conocidos
- Empaquetar Playwright junto al ejecutable puede requerir pasos adicionales (copiar runtime del navegador). Si quieres que lo gestione, puedo agregar instrucciones detalladas.

Uso rápido
- Ejecuta `Scraper_WEB.exe` o `python SCRAPER_WEB.py`.

Si quieres, preparo un script `build.ps1` que automatice los pasos de build y verificación.
