[CmdletBinding()]
param(
    [string]$AdbPath = "adb",
    [string]$Serial,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

function Invoke-AdbRead {
    param([string[]]$Arguments)

    $lines = @(& $script:AdbPath @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $text = ($lines | ForEach-Object { $_.ToString() }) -join "`n"
    if ($exitCode -ne 0) {
        throw "adb $($Arguments -join ' ') failed with exit code ${exitCode}: $text"
    }
    return $text.Trim()
}

function Invoke-AdbReadOptional {
    param([string[]]$Arguments)

    $lines = @(& $script:AdbPath @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $text = ($lines | ForEach-Object { $_.ToString() }) -join "`n"
    if ($exitCode -ne 0) {
        return $null
    }
    return $text.Trim()
}

$deviceList = Invoke-AdbRead @("devices", "-l")
$connectedDevices = @(
    foreach ($line in ($deviceList -split "`r?`n")) {
        if ($line -match '^([^\s]+)\s+device(?:\s|$)') {
            $Matches[1]
        }
    }
)

if (-not $Serial) {
    if ($connectedDevices.Count -ne 1) {
        throw "Expected exactly one authorized ADB device; found $($connectedDevices.Count). Pass -Serial explicitly."
    }
    $Serial = $connectedDevices[0]
}
if ($connectedDevices -notcontains $Serial) {
    throw "The requested ADB serial is not connected and authorized."
}

$model = Invoke-AdbRead @("-s", $Serial, "shell", "getprop", "ro.product.model")
$device = Invoke-AdbRead @("-s", $Serial, "shell", "getprop", "ro.product.device")
$soc = Invoke-AdbRead @("-s", $Serial, "shell", "getprop", "ro.soc.model")
$androidBuild = Invoke-AdbRead @("-s", $Serial, "shell", "getprop", "ro.build.version.incremental")
$bootloaderLocked = Invoke-AdbRead @("-s", $Serial, "shell", "getprop", "ro.boot.flash.locked")

if ($device -ne "nabu" -or $model -ne "21051182G") {
    throw "Refusing to record a non-target device: model=$model device=$device"
}

$cpuInfo = Invoke-AdbRead @("-s", $Serial, "shell", "cat", "/proc/cpuinfo")
$cpuRecords = @()
$currentCpu = $null
foreach ($line in ($cpuInfo -split "`r?`n")) {
    if ($line -match '^processor\s*:\s*(\d+)') {
        if ($null -ne $currentCpu) { $cpuRecords += $currentCpu }
        $currentCpu = [ordered]@{ cpu = [int]$Matches[1]; paca = $false; pacg = $false; features = @() }
    } elseif ($line -match '^Features\s*:\s*(.*)' -and $null -ne $currentCpu) {
        $features = @($Matches[1] -split '\s+' | Where-Object { $_ })
        $currentCpu.features = $features
        $currentCpu.paca = $features -contains "paca"
        $currentCpu.pacg = $features -contains "pacg"
    }
}
if ($null -ne $currentCpu) { $cpuRecords += $currentCpu }

$midr = @{}
foreach ($cpu in $cpuRecords) {
    $path = "/sys/devices/system/cpu/cpu$($cpu.cpu)/regs/identification/midr_el1"
    $midr[[string]$cpu.cpu] = Invoke-AdbReadOptional @("-s", $Serial, "shell", "cat", $path)
}

$isar1 = Invoke-AdbReadOptional @("-s", $Serial, "shell", "cat", "/sys/devices/system/cpu/cpu0/regs/identification/id_aa64isar1_el1")
$isar2 = Invoke-AdbReadOptional @("-s", $Serial, "shell", "cat", "/sys/devices/system/cpu/cpu0/regs/identification/id_aa64isar2_el1")
$missingPacFlags = @($cpuRecords | Where-Object { -not $_.paca -or -not $_.pacg }).Count

$report = [ordered]@{
    schema = "nabu-macos27-pac-preflight-v1"
    collected_utc = [DateTime]::UtcNow.ToString("o")
    device = [ordered]@{
        model = $model
        product = $device
        soc = $soc
        android_build = $androidBuild
        bootloader_locked = ($bootloaderLocked -eq "1")
    }
    cpu = [ordered]@{
        count = $cpuRecords.Count
        linux_features = $cpuRecords
        midr_el1 = $midr
        id_aa64isar1_el1 = $isar1
        id_aa64isar2_el1 = $isar2
        cpus_missing_paca_or_pacg = $missingPacFlags
    }
    target = "macos-27.3-26C5035r (arm64e)"
    assessment = if ($cpuRecords.Count -eq 0) { "incomplete" } elseif ($missingPacFlags -gt 0) { "linux_reports_pac_unavailable_on_some_cpus" } else { "linux_reports_pac_on_all_cpus_but_arm64e_checks_incomplete" }
    caveat = "Linux feature flags are an indirect report. They do not replace UniXNU's EL1 ID-register, key-write, and PAC instruction checks on every core."
    writes_performed = $false
}

$json = $report | ConvertTo-Json -Depth 8
if ($OutputPath) {
    $fullOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
    $parent = [System.IO.Path]::GetDirectoryName($fullOutputPath)
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Set-Content -LiteralPath $fullOutputPath -Value $json -Encoding UTF8
}
$json
