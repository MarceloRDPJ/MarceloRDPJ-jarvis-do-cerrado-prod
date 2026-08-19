<#
.SYNOPSIS
    Desativa aplicativos no Poco de forma reversível, com confirmação explícita.

.DESCRIPTION
    Usa 'pm disable-user --user 0', que é REVERSÍVEL por 'pm enable'. Nunca usa
    'pm uninstall': nada é removido de fato e nenhum dado de usuário é apagado.

    O script exige uma lista curada por você a partir do relatório gerado por
    poco_usb_inventory.ps1. Antes de agir, imprime exatamente o que fará e espera
    você digitar a confirmação. Ao final grava um script de desfazer.

    Pacotes essenciais ao aparelho e ao ROD estão protegidos e são recusados mesmo
    que apareçam na lista.

.PARAMETER PackageList
    Arquivo texto com um pacote por linha. Linhas vazias e começadas por # são ignoradas.

.PARAMETER WhatIf
    Mostra o plano e sai sem tocar no aparelho.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\poco_usb_disable_apps.ps1 -PackageList minha-lista.txt -WhatIf
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PackageList,
    [switch]$WhatIf,
    [string]$OutputDir
)

$ErrorActionPreference = 'Stop'

# $PSScriptRoot nao esta populado dentro do bloco param() no PowerShell 5.1.
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath) }
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot '.tools\poco-reports' }

# Rede de segurança: um erro de digitação aqui não pode inutilizar o aparelho
# nem derrubar o próprio nó do ROD.
$Protected = @(
    'br.com.jarviscerrado.poco',
    'br.com.saneago',
    'com.android.chrome',
    'com.android.systemui',
    'com.android.settings',
    'com.android.phone',
    'com.android.server.telecom',
    'com.android.providers.settings',
    'com.android.providers.media',
    'com.android.providers.contacts',
    'com.android.providers.downloads',
    'com.android.permissioncontroller',
    'com.android.bluetooth',
    'com.android.nfc',
    'com.android.keychain',
    'com.google.android.gms',
    'com.google.android.gsf',
    'com.google.android.packageinstaller',
    'com.google.android.webview',
    'com.android.vending',
    'com.miui.securitycenter',
    'com.miui.home',
    'com.lbe.security.miui',
    'com.xiaomi.xmsf'
)

function Resolve-Adb {
    $candidates = @()
    if ($env:ANDROID_HOME) { $candidates += (Join-Path $env:ANDROID_HOME 'platform-tools\adb.exe') }
    $candidates += (Join-Path $PSScriptRoot '..\.tools\platform-tools\adb.exe')
    $candidates += (Join-Path $PSScriptRoot '..\.tools\android-sdk\platform-tools\adb.exe')
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    $onPath = Get-Command adb -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    throw "adb não encontrado. Baixe o Platform Tools ou defina ANDROID_HOME."
}

if (-not (Test-Path $PackageList)) { throw "Lista não encontrada: $PackageList" }
$adb = Resolve-Adb

$devices = & $adb devices | Select-Object -Skip 1 | Where-Object { $_.Trim() -ne '' }
if (-not $devices) { throw "Nenhum aparelho conectado." }
if ($devices -match 'unauthorized') { throw "Aparelho não autorizado. Aceite a depuração USB no Poco." }

$requested = Get-Content $PackageList |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne '' -and -not $_.StartsWith('#') } |
    Sort-Object -Unique

if (-not $requested) { throw "A lista não contém nenhum pacote." }

$installed = (& $adb shell pm list packages) | ForEach-Object { $_ -replace '^package:', '' } | ForEach-Object { $_.Trim() }
$alreadyOff = (& $adb shell pm list packages -d) | ForEach-Object { $_ -replace '^package:', '' } | ForEach-Object { $_.Trim() }

$plan = @()
$refused = @()
$skipped = @()

foreach ($package in $requested) {
    if ($Protected -contains $package) {
        $refused += $package
    } elseif ($installed -notcontains $package) {
        $skipped += "$package (não instalado)"
    } elseif ($alreadyOff -contains $package) {
        $skipped += "$package (já desativado)"
    } else {
        $plan += $package
    }
}

Write-Host ""
Write-Host "=== PLANO ===" -ForegroundColor Cyan
Write-Host "Método: pm disable-user --user 0  (REVERSÍVEL, não apaga dados)" -ForegroundColor DarkGray
Write-Host ""

if ($refused) {
    Write-Host "RECUSADOS (protegidos):" -ForegroundColor Yellow
    foreach ($package in $refused) { Write-Host "  - $package" }
    Write-Host ""
}
if ($skipped) {
    Write-Host "IGNORADOS:" -ForegroundColor DarkGray
    foreach ($package in $skipped) { Write-Host "  - $package" }
    Write-Host ""
}
if (-not $plan) {
    Write-Host "Nada a fazer." -ForegroundColor Green
    exit 0
}

Write-Host "SERÃO DESATIVADOS ($($plan.Count)):" -ForegroundColor Yellow
foreach ($package in $plan) { Write-Host "  - $package" }
Write-Host ""

if ($WhatIf) {
    Write-Host "Modo -WhatIf: nada foi alterado no aparelho." -ForegroundColor Cyan
    exit 0
}

Write-Host "Digite exatamente CONFIRMO para prosseguir (qualquer outra coisa cancela):" -ForegroundColor Yellow
$answer = Read-Host
if ($answer -ne 'CONFIRMO') {
    Write-Host "Cancelado. Nada foi alterado." -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$undoPath = Join-Path $OutputDir "poco-desfazer-$stamp.ps1"

$done = @()
$failed = @()
foreach ($package in $plan) {
    $output = (& $adb shell pm disable-user --user 0 $package) -join ' '
    if ($output -match 'new state: disabled') {
        Write-Host "  desativado: $package" -ForegroundColor Green
        $done += $package
    } else {
        Write-Host "  FALHOU: $package -> $output" -ForegroundColor Red
        $failed += $package
    }
}

$undo = New-Object System.Collections.Generic.List[string]
$undo.Add("# Desfaz a desativação feita em $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')")
$undo.Add('$adb = ' + "'$adb'")
foreach ($package in $done) { $undo.Add("& `$adb shell pm enable $package") }
Set-Content -Path $undoPath -Value $undo -Encoding utf8

Write-Host ""
Write-Host "Desativados: $($done.Count)   Falhas: $($failed.Count)" -ForegroundColor Cyan
Write-Host "Para reverter tudo: $undoPath" -ForegroundColor Green
