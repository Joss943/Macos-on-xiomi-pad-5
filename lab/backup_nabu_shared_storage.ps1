[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $BackupDirectory,

    [string] $Serial
)

$ErrorActionPreference = 'Stop'

# Find adb on PATH, or the user-scope WinGet installation used by this project.
$adbCommand = Get-Command adb.exe -ErrorAction SilentlyContinue
$adbPath = if ($adbCommand) { $adbCommand.Source } else { $null }
if (-not $adbPath -and $env:LOCALAPPDATA) {
    $packageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (Test-Path -LiteralPath $packageRoot) {
        $platformTools = Get-ChildItem -LiteralPath $packageRoot -Directory -Filter 'Google.PlatformTools*' |
            Select-Object -First 1
        if ($platformTools) {
            $candidate = Join-Path $platformTools.FullName 'platform-tools\adb.exe'
            if (Test-Path -LiteralPath $candidate) { $adbPath = $candidate }
        }
    }
}
if (-not $adbPath) { throw 'ADB introuvable. Installe Google Android Platform Tools puis relance PowerShell.' }

$deviceList = @(& $adbPath devices -l)
if ($LASTEXITCODE -ne 0) { throw 'Impossible de lire la liste ADB.' }
$authorized = @(
    foreach ($line in $deviceList) {
        if ($line -match '^([^\s]+)\s+device(?:\s|$)') { $Matches[1] }
    }
)
if (-not $Serial) {
    if ($authorized.Count -ne 1) {
        throw "Il faut exactement une tablette autorisée par ADB. État actuel : $($deviceList -join '; ')"
    }
    $Serial = $authorized[0]
} elseif ($authorized -notcontains $Serial) {
    throw "La tablette $Serial n'est pas autorisée par ADB. Accepte d'abord la demande de débogage USB sur l'écran."
}

function Invoke-AdbText {
    param([Parameter(Mandatory = $true)][string[]] $AdbArgs)
    $result = @(& $script:adbPath -s $script:Serial @AdbArgs)
    if ($LASTEXITCODE -ne 0) {
        throw "ADB a échoué : $($AdbArgs -join ' ')"
    }
    return ($result -join "`n").Trim()
}

$device = Invoke-AdbText -AdbArgs @('shell', 'getprop', 'ro.product.device')
if ($device -ne 'nabu') {
    throw "Appareil détecté : '$device'. Cette sauvegarde n'est prévue que pour nabu / Xiaomi Pad 5."
}

# Xiaomi local backup can include app data. Require it before copying or proceeding.
$miuiBackup = Invoke-AdbText -AdbArgs @(
    'shell', 'sh', '-c',
    'if [ -d /sdcard/MIUI/backup/AllBackup ] && [ "$(ls -A /sdcard/MIUI/backup/AllBackup 2>/dev/null)" ]; then echo present; else echo missing; fi'
)
if ($miuiBackup -ne 'present') {
    throw 'Sauvegarde MIUI locale absente ou vide. Crée-la sur la tablette, puis relance ce script.'
}

$usage = Invoke-AdbText -AdbArgs @('shell', 'du', '-sk', '/sdcard')
if ($usage -notmatch '^\s*(\d+)\s') { throw "Taille de /sdcard illisible : $usage" }
$estimatedBytes = [int64]$Matches[1] * 1KB
$requiredBytes = [int64]($estimatedBytes * 1.2) + 1GB

$target = [System.IO.Path]::GetFullPath($BackupDirectory)
$driveRoot = [System.IO.Path]::GetPathRoot($target)
$drive = [System.IO.DriveInfo]::new($driveRoot)
if ($drive.AvailableFreeSpace -lt $requiredBytes) {
    $freeGiB = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    $needGiB = [math]::Round($requiredBytes / 1GB, 1)
    throw "Espace insuffisant sur $driveRoot : $freeGiB Gio libres, environ $needGiB Gio nécessaires."
}
if (Test-Path -LiteralPath $target) {
    if (@(Get-ChildItem -LiteralPath $target -Force).Count -gt 0) {
        throw "Le dossier de sauvegarde existe et n'est pas vide : $target"
    }
} else {
    New-Item -ItemType Directory -Path $target | Out-Null
}

$model = Invoke-AdbText -AdbArgs @('shell', 'getprop', 'ro.product.model')
$androidVersion = Invoke-AdbText -AdbArgs @('shell', 'getprop', 'ro.build.version.release')
$build = Invoke-AdbText -AdbArgs @('shell', 'getprop', 'ro.build.version.incremental')
$metadata = @(
    "Device: $device"
    "Model: $model"
    "Android: $androidVersion"
    "Build: $build"
    "Created UTC: $([DateTime]::UtcNow.ToString('o'))"
    'Scope: MIUI local backup and shared /sdcard storage'
    'Excluded: Android system partitions and private app data outside the MIUI backup archive'
)
[System.IO.File]::WriteAllLines(
    (Join-Path $target 'backup-info.txt'),
    $metadata,
    [System.Text.UTF8Encoding]::new($false)
)

$sharedStorage = Join-Path $target 'shared-storage'
& $adbPath -s $Serial pull /sdcard $sharedStorage
if ($LASTEXITCODE -ne 0) { throw 'ADB pull a échoué; ne déverrouille pas le bootloader et ne supprime rien.' }

$miuiLocalCopy = Join-Path $sharedStorage 'MIUI\backup\AllBackup'
if (-not (Test-Path -LiteralPath $miuiLocalCopy) -or
    @(Get-ChildItem -LiteralPath $miuiLocalCopy -File -Recurse -ErrorAction Stop).Count -eq 0) {
    throw 'La copie MIUI est absente ou vide après transfert; ne déverrouille pas le bootloader.'
}

$files = @(Get-ChildItem -LiteralPath $sharedStorage -File -Recurse -ErrorAction Stop)
$hashLines = foreach ($file in $files) {
    $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
    $relativePath = $file.FullName.Substring($sharedStorage.Length).TrimStart('\')
    "$($hash.Hash)  $relativePath"
}
[System.IO.File]::WriteAllLines(
    (Join-Path $target 'SHA256SUMS.txt'),
    @($hashLines),
    [System.Text.UTF8Encoding]::new($false)
)

$totalBytes = ($files | Measure-Object -Property Length -Sum).Sum
Write-Output "Sauvegarde copiée et indexée : $target"
Write-Output "Fichiers : $($files.Count); octets : $totalBytes"
Write-Output 'Elle contient le stockage partagé et la sauvegarde MIUI. Elle ne remplace pas une sauvegarde des partitions système.'
