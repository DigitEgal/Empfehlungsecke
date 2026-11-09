#requires -Version 5.1
<#!
.SYNOPSIS
    Richtet die DigitEgal Empfehlungsecke ohne Administratorrechte ein.

.DESCRIPTION
    Die Anwendung verwendet nur die Python-Standardbibliothek (inklusive
    tkinter). Das Skript installiert bei Bedarf Python 3.11 per winget und
    legt daneben eine lokale virtuelle Umgebung an. Es werden keine externen
    Python-Pakete benötigt oder aus dem Internet geladen.
#>

[CmdletBinding()]
param(
    [switch]$Start
)

$ErrorActionPreference = "Stop"
$appFolder = $PSScriptRoot
$venvFolder = Join-Path $appFolder ".venv"
$venvPython = Join-Path $venvFolder "Scripts\python.exe"

function Test-Python {
    param(
        [Parameter(Mandatory)] [string]$Executable,
        [string[]]$Arguments = @()
    )

    try {
        & $Executable @Arguments -c "import sys, tkinter; assert sys.version_info >= (3, 9)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-Python {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher -and (Test-Python -Executable $launcher.Source -Arguments @("-3"))) {
        return @{ Executable = $launcher.Source; Arguments = @("-3") }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and (Test-Python -Executable $python.Source)) {
        return @{ Executable = $python.Source; Arguments = @() }
    }

    $localPythonFolder = Join-Path $env:LocalAppData "Programs\Python"
    if (Test-Path -LiteralPath $localPythonFolder) {
        $candidates = Get-ChildItem -LiteralPath $localPythonFolder -Filter "python.exe" -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending
        foreach ($candidate in $candidates) {
            if (Test-Python -Executable $candidate.FullName) {
                return @{ Executable = $candidate.FullName; Arguments = @() }
            }
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath (Join-Path $appFolder "app.py"))) {
    throw "app.py wurde neben dem Installationsskript nicht gefunden."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $python = Find-Python
    if (-not $python) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw "Python wurde nicht gefunden und winget ist nicht verfügbar. Bitte Python 3.9 oder neuer von https://www.python.org/downloads/windows/ installieren und dieses Skript erneut starten."
        }

        Write-Host "Python 3.11 wird installiert …" -ForegroundColor Cyan
        & $winget.Source install --id Python.Python.3.11 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "Die Python-Installation über winget ist fehlgeschlagen."
        }
        $python = Find-Python
        if (-not $python) {
            throw "Python wurde installiert, ist aber noch nicht auffindbar. Bitte dieses Skript erneut starten."
        }
    }

    Write-Host "Lokale Umgebung wird vorbereitet …" -ForegroundColor Cyan
    & $python.Executable @($python.Arguments) -m venv $venvFolder
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw "Die lokale Python-Umgebung konnte nicht angelegt werden."
    }
}

if (-not (Test-Python -Executable $venvPython)) {
    throw "Die lokale Python-Umgebung enthält kein funktionsfähiges tkinter."
}

Write-Host "`nInstallation abgeschlossen." -ForegroundColor Green
Write-Host "Start: starten.bat" -ForegroundColor White
Write-Host "Die Link-Sammlung kann später in der App über 'Ordner wählen' gewechselt werden." -ForegroundColor DarkGray

if ($Start) {
    Start-Process -FilePath $venvPython -ArgumentList 'app.py' -WorkingDirectory $appFolder
}
