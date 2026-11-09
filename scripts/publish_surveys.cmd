@echo off
REM publish_surveys.cmd - rebuild the static sentiment page and publish it to
REM surveys.bluemagicai.com. The Windows twin of publish_surveys.sh, for the box that
REM produces every store (NUCBOX_M8), so the page is built from the stores where they
REM are written rather than from a replica a /MIR sync is still delivering.
REM
REM Called by dbmf-tracker's deploy\publish_all.cmd, beside the DBMF, AHLT and ORR
REM pages, so it runs on that file's schedule (weekdays 08:30 and 18:00, the DBMF
REM Tracker tasks, as SYSTEM) and by hand whenever publish_all is run. The 18:00 run
REM is the one that matters: it follows the 17:30 equities task, which writes SPY and
REM builds NAAIM and its provisional weeks. An unchanged page pushes nothing, so the
REM extra morning run costs one render.
REM
REM Two steps, each owned elsewhere:
REM   1. scripts\export_sentiment_page.py renders the page from the stores, and
REM      writes nothing (exit 1) when a read is empty.
REM   2. dbmf-tracker's deploy\publish_pages.py --key surveys pushes it to the clone
REM      of mspinola/surveys-dashboard, carrying the CNAME forward.
REM
REM Every path is absolute and set here, because SYSTEM has no profile and reads no
REM .env: an unset store variable raises inside the stores, and an unset
REM COTMETRICS_PARAMS silently reads a 6-symbol sample. Each is overridable by setting
REM it before calling. ONE machine publishes: do not also schedule the Mac's
REM publish_surveys.sh, since each publish force-pushes a single-commit branch.
REM
REM One-time setup on the box is in docs\surveys-publishing.md.
REM
REM Do NOT put angle brackets anywhere in this file, comments included: cmd reads them
REM as redirection. Exit codes are captured on their own line after each command,
REM because %ERRORLEVEL% on the same line expands before the command runs.
setlocal
set "CODE=C:\Users\matt\code"
if "%CA%"=="" set "CA=%CODE%\cot-analyzer"
if "%DBMF_PROJ%"=="" set "DBMF_PROJ=%CODE%\dbmf-tracker-windows-bundle"
if "%SURVEYS_PAGES%"=="" set "SURVEYS_PAGES=%CODE%\surveys-dashboard"
if "%COTDATA_STORE%"=="" set "COTDATA_STORE=%CODE%\cotdata_store"
if "%MARKETDATA_STORE%"=="" set "MARKETDATA_STORE=%CODE%\marketdata_store"
if "%COTMETRICS_PARAMS%"=="" set "COTMETRICS_PARAMS=%CODE%\cotmetrics-config\params.yaml"
if "%COT_VIZ_CONFIG%"=="" set "COT_VIZ_CONFIG=%COTMETRICS_PARAMS%"
set "STATE=%CODE%\.local-state\cot-analyzer"
if "%COTMETRICS_CACHE%"=="" set "COTMETRICS_CACHE=%STATE%\data_cache"
if "%COTMETRICS_LOG_DIR%"=="" set "COTMETRICS_LOG_DIR=%STATE%\logs"
if "%COTMETRICS_DB%"=="" set "COTMETRICS_DB=%STATE%\cot_data.db"
set "COT_SKIP_BOOT_FETCH=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%CA%\src"

set "CAPY=%CA%\.venv\Scripts\python.exe"
set "PUBPY=%DBMF_PROJ%\.venv\Scripts\python.exe"
set "PUB=%DBMF_PROJ%\deploy\publish_pages.py"
set "OUT=%STATE%\surveys.html"

if not exist "%CAPY%" (
  echo publish_surveys: no venv at %CA%\.venv - see docs\surveys-publishing.md
  exit /b 1
)
if not exist "%COTMETRICS_PARAMS%" (
  echo publish_surveys: no %COTMETRICS_PARAMS% - refusing to render from the sample universe
  exit /b 1
)
if not exist "%SURVEYS_PAGES%\.git" (
  echo publish_surveys: no clone at %SURVEYS_PAGES%
  exit /b 1
)
if not exist "%STATE%\data_cache" mkdir "%STATE%\data_cache"
if not exist "%STATE%\logs" mkdir "%STATE%\logs"

cd /d "%CA%"
"%CAPY%" scripts\export_sentiment_page.py "%OUT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo publish_surveys: export failed with code %RC%, published page left as it was
  exit /b %RC%
)
"%PUBPY%" "%PUB%" --dashboard "%OUT%" --key surveys --pages-dir "%SURVEYS_PAGES%" %*
set "RC=%ERRORLEVEL%"
exit /b %RC%
