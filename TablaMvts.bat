@echo OFF

rem Define here the path to your conda installation
set CONDAPATH=C:\ProgramData\anaconda3
rem Define here the name of the environment
set ENVNAME=geofolia

rem The following command activates the base environment.

if %ENVNAME%==base (set ENVPATH=%CONDAPATH%) else (set ENVPATH=%CONDAPATH%\envs\%ENVNAME%)

rem Activate the conda environment
call %CONDAPATH%\Scripts\activate.bat %ENVPATH%

rem Run a python script in that environment
python C:\Users\Administrador\Documents\scripts_isagri\TablaMvts\__init__.py

rem Deactivate the environment
call conda deactivate
