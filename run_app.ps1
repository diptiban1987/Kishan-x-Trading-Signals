Write-Host "Starting Trading Platform..." -ForegroundColor Green
Write-Host ""

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

Write-Host ""
Write-Host "Starting Flask application..." -ForegroundColor Yellow
python app.py

Write-Host ""
Write-Host "Application stopped." -ForegroundColor Red
Read-Host "Press Enter to exit"
