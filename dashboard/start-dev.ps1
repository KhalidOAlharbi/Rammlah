$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$nodeDir = Get-ChildItem -LiteralPath "..\.tools" -Directory -Filter "node-*-win-x64" |
    Sort-Object Name -Descending |
    Select-Object -First 1

if ($null -eq $nodeDir) {
    throw "Portable Node.js was not found under .tools. Ask Codex to reinstall the local Node toolchain."
}

$env:Path = "$($nodeDir.FullName);$env:Path"

& (Join-Path $nodeDir.FullName "npm.cmd") install
& (Join-Path $nodeDir.FullName "npm.cmd") run dev -- --host 127.0.0.1 --port 5173
