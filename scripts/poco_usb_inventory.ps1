<#
.SYNOPSIS
    Inventário somente leitura do Poco conectado por USB.

.DESCRIPTION
    Primeiro passo da preparação do nó Android. Este script NÃO altera nada no
    aparelho: não instala, não desinstala, não desativa, não apaga e não mexe em
    contas. Ele apenas coleta o estado atual e grava um relatório para que a
    decisão sobre o que remover seja tomada com a lista na mão.

    Nada de segredo é coletado: senhas de Wi-Fi, conteúdo do cofre do ROD, tokens
    e dados de aplicativos ficam de fora por construção.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\poco_usb_inventory.ps1
#>

[CmdletBinding()]
param(
    [string]$OutputDir
)

$ErrorActionPreference = 'Stop'

# $PSScriptRoot nao esta populado dentro do bloco param() no PowerShell 5.1.
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath) }
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot '.tools\poco-reports' }

function Resolve-Adb {
    $candidates = @()
    if ($env:ANDROID_HOME) { $candidates += (Join-Path $env:ANDROID_HOME 'platform-tools\adb.exe') }
    if ($env:ANDROID_SDK_ROOT) { $candidates += (Join-Path $env:ANDROID_SDK_ROOT 'platform-tools\adb.exe') }
    $candidates += (Join-Path $PSScriptRoot '..\.tools\platform-tools\adb.exe')
    $candidates += (Join-Path $PSScriptRoot '..\.tools\android-sdk\platform-tools\adb.exe')
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    $onPath = Get-Command adb -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    throw "adb não encontrado. Baixe o Platform Tools ou defina ANDROID_HOME."
}

$adb = Resolve-Adb
Write-Host "adb: $adb" -ForegroundColor DarkGray

# --- Estado da conexão -----------------------------------------------------
$devices = & $adb devices | Select-Object -Skip 1 | Where-Object { $_.Trim() -ne '' }
if (-not $devices) {
    Write-Host ""
    Write-Host "Nenhum aparelho detectado." -ForegroundColor Yellow
    Write-Host "Confira o cabo, escolha 'Transferência de arquivos' no Poco e ative a Depuração USB."
    exit 1
}
if ($devices -match 'unauthorized') {
    Write-Host ""
    Write-Host "Aparelho detectado, mas NÃO autorizado." -ForegroundColor Yellow
    Write-Host "No Poco: desbloqueie a tela, marque 'Sempre permitir deste computador' e toque em Permitir."
    Write-Host "Se a janela não aparecer: Opções do desenvolvedor > Revogar autorizações de depuração USB,"
    Write-Host "depois desligue e ligue a Depuração USB e reconecte o cabo."
    exit 1
}
if ($devices -match 'offline') {
    Write-Host "Aparelho offline para o adb. Reconecte o cabo e rode de novo." -ForegroundColor Yellow
    exit 1
}

function Get-Prop([string]$name) {
    $value = (& $adb shell getprop $name) -join ''
    return $value.Trim()
}

function Invoke-Device([string]$command) {
    try { return (& $adb shell $command) -join [Environment]::NewLine }
    catch { return "(indisponível: $($_.Exception.Message))" }
}

Write-Host "Coletando inventário (somente leitura)..." -ForegroundColor Cyan

$model         = Get-Prop 'ro.product.model'
$codename      = Get-Prop 'ro.product.device'
$androidLevel  = Get-Prop 'ro.build.version.release'
$sdk           = Get-Prop 'ro.build.version.sdk'
$securityPatch = Get-Prop 'ro.build.version.security_patch'
$miui          = Get-Prop 'ro.miui.ui.version.name'
$buildId       = Get-Prop 'ro.build.version.incremental'

$battery      = Invoke-Device 'dumpsys battery'
$storage      = Invoke-Device 'df -h /data /storage/emulated'
$thirdParty   = (& $adb shell pm list packages -3) | ForEach-Object { $_ -replace '^package:', '' } | Sort-Object
$disabled     = (& $adb shell pm list packages -d) | ForEach-Object { $_ -replace '^package:', '' } | Sort-Object
$systemCount  = ((& $adb shell pm list packages -s) | Measure-Object).Count
$accessibility = Invoke-Device 'settings get secure enabled_accessibility_services'
$dozeWhitelist = Invoke-Device 'dumpsys deviceidle whitelist'

# Volume de mídia: apenas contagem e tamanho, nunca o conteúdo.
$dcimCount = Invoke-Device 'find /sdcard/DCIM -type f 2>/dev/null | wc -l'
$dcimSize  = Invoke-Device 'du -sh /sdcard/DCIM 2>/dev/null'
$downloads = Invoke-Device 'du -sh /sdcard/Download 2>/dev/null'
$whatsapp  = Invoke-Device 'du -sh /sdcard/Android/media/com.whatsapp 2>/dev/null'

$interesting = @(
    'br.com.jarviscerrado.poco',
    'br.com.saneago',
    'com.android.chrome'
)
$presence = foreach ($package in $interesting) {
    $version = Invoke-Device "dumpsys package $package | grep versionName | head -1"
    $state = if ($version -match 'versionName') { $version.Trim() } else { 'NÃO INSTALADO' }
    [PSCustomObject]@{ Pacote = $package; Estado = $state }
}

# --- Relatório -------------------------------------------------------------
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$reportPath = Join-Path $OutputDir "poco-inventario-$stamp.txt"

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("INVENTÁRIO DO POCO - $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')")
$lines.Add("Coleta somente leitura. Nenhuma alteração foi feita no aparelho.")
$lines.Add('')
$lines.Add('== APARELHO ==')
$lines.Add("Modelo............: $model")
$lines.Add("Codinome..........: $codename")
$lines.Add("Android...........: $androidLevel (SDK $sdk)")
$lines.Add("Patch de seguranca: $securityPatch")
$lines.Add("MIUI..............: $miui")
$lines.Add("Build.............: $buildId")
$lines.Add('')
$lines.Add('== BATERIA ==')
$lines.Add($battery)
$lines.Add('')
$lines.Add('== ARMAZENAMENTO ==')
$lines.Add($storage)
$lines.Add('')
$lines.Add('== MÍDIA (volume, sem conteúdo) ==')
$lines.Add("Arquivos em DCIM..: $dcimCount")
$lines.Add("Tamanho DCIM......: $dcimSize")
$lines.Add("Tamanho Download..: $downloads")
$lines.Add("Mídia WhatsApp....: $whatsapp")
$lines.Add('')
$lines.Add('== APLICATIVOS RELEVANTES PARA O ROD ==')
foreach ($item in $presence) { $lines.Add(("{0,-32} {1}" -f $item.Pacote, $item.Estado)) }
$lines.Add('')
$lines.Add('== ACESSIBILIDADE ATIVA ==')
$lines.Add($accessibility)
$lines.Add('')
$lines.Add('== ISENTOS DE OTIMIZAÇÃO DE BATERIA ==')
$lines.Add($dozeWhitelist)
$lines.Add('')
$lines.Add("== APLICATIVOS DE TERCEIROS ($($thirdParty.Count)) ==")
foreach ($package in $thirdParty) { $lines.Add($package) }
$lines.Add('')
$lines.Add("== JÁ DESATIVADOS ($($disabled.Count)) ==")
foreach ($package in $disabled) { $lines.Add($package) }
$lines.Add('')
$lines.Add("== PACOTES DE SISTEMA: $systemCount (não listados; use 'adb shell pm list packages -s') ==")

Set-Content -Path $reportPath -Value $lines -Encoding utf8

Write-Host ""
Write-Host "Aparelho.....: $model ($codename)" -ForegroundColor Green
Write-Host "Android......: $androidLevel / MIUI $miui"
Write-Host "Terceiros....: $($thirdParty.Count) aplicativos"
Write-Host "Desativados..: $($disabled.Count) aplicativos"
Write-Host ""
Write-Host "Relatório: $reportPath" -ForegroundColor Green
Write-Host ""
Write-Host "Nada foi alterado no Poco. Revise a lista antes de qualquer remoção." -ForegroundColor Cyan
