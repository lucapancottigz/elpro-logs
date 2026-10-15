@echo off
rem Copyright (c) 2026 Geoazimut SàRL. Tous droits réservés.
rem Construit dist\ELPRO Logs\, dist\ELPRO_Logs.zip et l'installateur (venv cree selon docs\01_Architecture.md)
cd /d "%~dp0"
set PY=.\venv\Scripts\python.exe
if not exist %PY% (echo venv introuvable : voir README.md & exit /b 1)

rem 1. Tests : arret au premier echec, avant PyInstaller
%PY% -m unittest discover -s tests -v || (echo ECHEC des tests du moteur & exit /b 1)
%PY% tests_ui\ui_acceptance.py || (echo ECHEC de la recette interface & exit /b 1)

rem 2. Executable (ressource de version Windows generee depuis version.py)
rem    --collect-data tzdata : obligatoire, sinon l'heure suisse n'est pas disponible dans l'executable
%PY% installer\make_version_info.py || (echo ECHEC version_info & exit /b 1)
%PY% -m PyInstaller --noconfirm --windowed --name "ELPRO Logs" --icon "resources\app_icon.ico" ^
  --version-file build\version_info.txt ^
  --add-data "engine;engine" --add-data "resources;resources" --add-data "examples;examples" ^
  --add-data "LICENSE;." --add-data "THIRD_PARTY_NOTICES.md;." ^
  --collect-data tzdata ^
  app.py || exit /b 1

rem 3. Verification depuis l'executable (import des logs de demo, heure suisse), puis zip du livrable
start "" /wait "dist\ELPRO Logs\ELPRO Logs.exe" --verifier "%TEMP%\elpro_logs_verif"
type "%TEMP%\elpro_logs_verif\verification.txt"
findstr /c:"CHEC" "%TEMP%\elpro_logs_verif\verification.txt" >nul && (echo ECHEC de la verification & exit /b 1)
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\ELPRO Logs' -DestinationPath 'dist\ELPRO_Logs.zip'"
echo Livrable : dist\ELPRO_Logs.zip

rem 4. Installateur (Inno Setup 6)
for /f "tokens=2 delims='" %%v in ('findstr /b "APP_VERSION" version.py') do set VER=%%v
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (echo Inno Setup 6 introuvable : installateur non cree & exit /b 1)
rem Licence affichee par l'installateur : texte UTF-8 avec BOM
powershell -NoProfile -Command "Get-Content LICENSE -Encoding UTF8 | Set-Content build\LICENSE.txt -Encoding UTF8" || (echo ECHEC LICENSE.txt & exit /b 1)
rem Anciens installateurs retires de dist\ : SHA256SUMS.txt ne couvre que la version construite
del /q "dist\ELPRO_Logs_Setup*.exe" 2>nul
%ISCC% /DAppVersion=%VER% installer\elpro_logs.iss || (echo ECHEC de l'installateur & exit /b 1)
echo Installateur : dist\ELPRO_Logs_Setup_%VER%.exe

rem 5. Copie de l'installateur sous un nom fixe (lien Telecharger du README)
copy /y "dist\ELPRO_Logs_Setup_%VER%.exe" "dist\ELPRO_Logs_Setup.exe" >nul || (echo ECHEC de la copie & exit /b 1)
rem 6. Empreintes SHA-256 des installateurs (publiees dans la release)
powershell -NoProfile -Command "Get-FileHash dist\ELPRO_Logs_Setup*.exe -Algorithm SHA256 | ForEach-Object { $_.Hash.ToLower() + '  ' + (Split-Path $_.Path -Leaf) } | Set-Content -Encoding ascii dist\SHA256SUMS.txt" || (echo ECHEC des empreintes & exit /b 1)
echo Release : dist\ELPRO_Logs_Setup.exe, dist\ELPRO_Logs_Setup_%VER%.exe, dist\SHA256SUMS.txt
