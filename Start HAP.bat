@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BACKEND_URL=http://127.0.0.1:8000"
set "FRONTEND_URL=http://localhost:3000"
set "PY="
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo HAP local launcher
echo Frontend: %FRONTEND_URL%
echo Backend:  %BACKEND_URL%
echo Storage:  backend\storage
echo Auth:     local default (disabled unless HAP_AUTH_ENABLED=true)
echo.

call :is_listening 127.0.0.1 8000
if %ERRORLEVEL%==0 (
  echo Backend already running on port 8000.
) else (
  echo Starting backend...
  start "HAP Backend" /D "%~dp0backend" cmd /k ""%PY%" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
)

call :is_listening 127.0.0.1 3000
if %ERRORLEVEL%==0 (
  echo Frontend already running on port 3000.
) else (
  echo Starting frontend...
  start "HAP Frontend" /D "%~dp0frontend" cmd /k "npm run dev -- --hostname 127.0.0.1 --port 3000"
)

echo Waiting for services...
call :wait_http %BACKEND_URL%/health 40
if %ERRORLEVEL% neq 0 (
  echo Backend did not become ready at %BACKEND_URL%/health
  echo Check the HAP Backend window.
  exit /b 1
)
call :wait_http http://127.0.0.1:3000 120
if %ERRORLEVEL% neq 0 (
  echo Frontend did not become ready at %FRONTEND_URL%
  echo Check the HAP Frontend window.
  exit /b 1
)

echo Opening %FRONTEND_URL%
start "" "%FRONTEND_URL%"
echo HAP is ready. Close the Backend and Frontend windows to stop.
exit /b 0

:is_listening
powershell -NoProfile -Command "$c=$null; try { $c=New-Object Net.Sockets.TcpClient; $c.ReceiveTimeout=500; $c.Connect('%~1',%~2); exit 0 } catch { exit 1 } finally { if ($c) { $c.Dispose() } }"
exit /b %ERRORLEVEL%

:wait_http
powershell -NoProfile -Command "$u='%~1'; $n=[int]'%~2'; for ($i=0; $i -lt $n; $i++) { try { $r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } } catch { }; Start-Sleep -Seconds 1 }; exit 1"
exit /b %ERRORLEVEL%
