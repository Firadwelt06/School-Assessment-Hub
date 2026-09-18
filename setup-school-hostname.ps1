param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIp,
    [string]$Hostname = "lahs.local"
)

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator, then run this script again."
}

$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$entry = "$ServerIp`t$Hostname"
$existing = Get-Content -Path $hostsPath -ErrorAction Stop
$hostnamePattern = "(?i)^\s*(?:\d{1,3}\.){3}\d{1,3}\s+$([regex]::Escape($Hostname))\s*$"
$existing = @($existing | Where-Object { $_ -notmatch $hostnamePattern })

Set-Content -Path $hostsPath -Value @($existing + $entry) -Encoding ascii -ErrorAction Stop

Clear-DnsClientCache -ErrorAction Stop
Write-Host "Configured $Hostname to use $ServerIp on this computer."
Write-Host "Open http://$Hostname`:5000"
