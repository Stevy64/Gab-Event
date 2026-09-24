@echo off
REM Raccourci Windows vers les cibles du Makefile
setlocal
set COMPOSE_DEV=docker compose -f docker-compose.dev.yml
set COMPOSE_PROD=docker compose -f docker-compose.yml
if "%1"=="" goto dev
if "%1"=="dev" goto dev
if "%1"=="up" goto dev
if "%1"=="prod" goto prod
if "%1"=="down" goto down
if "%1"=="stop" goto down
if "%1"=="restart" goto restart
if "%1"=="logs" goto logs
if "%1"=="migrate" goto migrate
if "%1"=="superuser" goto superuser
if "%1"=="clean" goto clean
if "%1"=="ps" goto ps
if "%1"=="health" goto health
echo Cibles: dev prod down restart logs migrate superuser clean ps health
exit /b 1

:dev
%COMPOSE_DEV% up --build
goto :eof

:prod
%COMPOSE_PROD% up --build -d
goto :eof

:down
%COMPOSE_DEV% down
%COMPOSE_PROD% down
goto :eof

:restart
%COMPOSE_DEV% down
%COMPOSE_DEV% up --build
goto :eof

:logs
%COMPOSE_DEV% logs -f
goto :eof

:migrate
%COMPOSE_DEV% exec gabevent-web python manage.py migrate --noinput
goto :eof

:superuser
%COMPOSE_DEV% exec gabevent-web python manage.py createsuperuser
goto :eof

:clean
%COMPOSE_DEV% down -v
%COMPOSE_PROD% down -v
goto :eof

:ps
%COMPOSE_DEV% ps
goto :eof

:health
%COMPOSE_DEV% exec gabevent-web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/').read().decode())"
goto :eof
