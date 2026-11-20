@echo off
rem HAP shortcut.   hap TICKER TYPE [PERIOD] [extra run_batch options]
rem   hap POWL annual 2026FY      annual update
rem   hap HCKT quarterly 2026Q3   quarterly update
rem   hap WWD new                 new company
rem Add --no-email at the end to skip the email.  Needs the Excel result files closed.
setlocal
if "%~2"=="" (
  echo Usage: hap TICKER annual^|quarterly^|new [PERIOD]   for example: hap POWL annual 2026FY
  exit /b 1
)
set "KIND=%~2"
if /i "%KIND%"=="annual" set "KIND=annual_update"
if /i "%KIND%"=="quarterly" set "KIND=quarterly_update"
if /i "%KIND%"=="q" set "KIND=quarterly_update"
if /i "%KIND%"=="new" set "KIND=new_company"
set "JOB=%~1:%KIND%"
set "REST=%~4 %~5 %~6"
if not "%~3"=="" (
  echo %~3| findstr /b /c:"--" >nul
  if errorlevel 1 ( set "JOB=%~1:%KIND%:%~3" ) else ( set "REST=%~3 %~4 %~5 %~6" )
)
cd /d "%~dp0backend"
python scripts/run_batch.py %JOB% --drive-folder "11G1oo5yI9kJVqcgycMEEWg9EI4ASUxG8,1SI8neXNQ_0A7TxGxn6Dny9ab0bt_-bkD,1qymwqO_YDkYCZBArrt4vx-CMz78aWjAU" --drive-previous 1IsgAZsumxtW0MPl4VeMJyYmhHMoWeIbo %REST%
endlocal
