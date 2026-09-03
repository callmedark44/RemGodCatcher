@echo off
rem Install the modified gallery-dl Zerochan extractor.
rem Adds page_html support for categorized tag parsing.
rem
rem Usage: install.bat
rem Requires: gallery-dl installed via pip

for /f "delims=" %%i in ('python -c "import gallery_dl, os; print(os.path.dirname(gallery_dl.__file__))" 2^>nul') do set SITE_PACKAGES=%%i
if "%SITE_PACKAGES%"=="" (
    echo Error: gallery-dl not found. Install it first:
    echo   pip install gallery-dl
    exit /b 1
)

set TARGET=%SITE_PACKAGES%\extractor\zerochan.py
if exist "%TARGET%" (
    echo Backing up original to %TARGET%.bak
    copy /y "%TARGET%" "%TARGET%.bak" >nul
)

copy /y "%~dp0zerochan.py" "%TARGET%" >nul
echo Installed patched zerochan.py to %TARGET%
echo Done. gallery-dl will now support --page-html for zerochan.
