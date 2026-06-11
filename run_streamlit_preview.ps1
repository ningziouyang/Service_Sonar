$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$streamlit = Join-Path $PSScriptRoot ".venv\Scripts\streamlit.exe"
& $streamlit run dashboard.py `
    --server.port 8501 `
    --server.address 127.0.0.1 `
    --server.headless true `
    --server.fileWatcherType none
