# Package the web app as a Windows program for people without Python.
# Output: dist\Course Accessibility Reports\ (run the .exe inside) and a .zip of that folder.
# Usage: .\build.ps1   (after setting up .venv as in the README)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".venv\Scripts\python.exe"
$name = "Course Accessibility Reports"

& $py -m pip install --quiet pyinstaller
# The Google API descriptions ship with the client library; bundle only the ones the app uses
# (Gmail for email import, Sheets and Drive for the department inventory), not every Google API's.
$docs = & $py -c "import googleapiclient, pathlib; print(pathlib.Path(googleapiclient.__file__).parent / 'discovery_cache/documents')"
$apis = "gmail.v1", "sheets.v4", "drive.v3" | ForEach-Object { "--add-data"; "$docs\$_.json;googleapiclient\discovery_cache\documents" }

& $py -m PyInstaller app.py --name $name --onedir --noconfirm --clean --specpath build `
    --add-data "$PSScriptRoot\templates;templates" `
    --add-data "$PSScriptRoot\static;static" `
    @apis `
    --exclude-module matplotlib
if ($LASTEXITCODE) { exit $LASTEXITCODE }

Compress-Archive -Path "dist\$name" -DestinationPath "dist\$name.zip" -Force
Write-Host "`nBuilt dist\$name\$name.exe and dist\$name.zip"
