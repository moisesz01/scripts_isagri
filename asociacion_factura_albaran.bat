@echo OFF
setlocal

rem Ruta de la instalacion de conda y nombre del entorno
set CONDAPATH=C:\ProgramData\anaconda3
set ENVNAME=geofolia

if %ENVNAME%==base (set ENVPATH=%CONDAPATH%) else (set ENVPATH=%CONDAPATH%\envs\%ENVNAME%)

rem Activar el entorno de conda
call "%CONDAPATH%\Scripts\activate.bat" "%ENVPATH%"

rem Ejecutar el script. %~dp0 es la carpeta donde esta este .bat, asi que
rem funciona sin importar donde se clone el repositorio ni desde donde se lance
python "%~dp0Compras\asociacion_factura_albaran_compras.py"

rem Guardar el codigo de salida de Python antes de desactivar el entorno,
rem para que el Programador de tareas sepa si fallo (0 = OK, 1 = error)
set EXITCODE=%ERRORLEVEL%

rem Desactivar el entorno
call conda deactivate

exit /b %EXITCODE%
