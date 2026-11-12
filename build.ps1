# Package the web app as a Windows program for people without Python.
# Output: dist\Course Accessibility Reports\ (run the .exe inside) and a .zip of that folder.
# Usage: .\build.ps1   (after setting up .venv as in the README)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".venv\Scripts\python.exe"
$name = "Course Accessibility Reports"

& $py -m pip install --quiet pyinstaller
# The Gmail API description ships with the client library; bundle only Gmail's, not every Google API's.
$gmail = & $py -c "import googleapiclient, pathlib; print(pathlib.Path(googleapiclient.__file__).parent / 'discovery_cache/documents/gmail.v1.json')"

& $py -m PyInstaller app.py --name $name --onedir --noconfirm --clean --specpath build `
    --add-data "$PSScriptRoot\templates;templates" `
    --add-data "$PSScriptRoot\static;static" `
    --add-data "$gmail;googleapiclient\discovery_cache\documents" `
    --exclude-module matplotlib
if ($LASTEXITCODE) { exit $LASTEXITCODE }

Compress-Archive -Path "dist\$name" -DestinationPath "dist\$name.zip" -Force
Write-Host "`nBuilt dist\$name\$name.exe and dist\$name.zip"
