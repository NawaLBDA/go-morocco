# Script de test de performance pour votre application Render
# Utilisation: .\performance_test.ps1 -Url "https://go-morocco.onrender.com" -Requests 10

param(
    [string]$Url = "https://go-morocco.onrender.com",
    [int]$Requests = 10
)

Write-Host "=== TEST DE PERFORMANCE - $Url ===" -ForegroundColor Green

$results = @()
$totalTime = 0
$successCount = 0
$minTime = [double]::MaxValue
$maxTime = 0

Write-Host "Test de reveil de l'application..." -ForegroundColor Yellow
try {
    $wakeResponse = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 60
    Write-Host "OK - Application reveillee - Status: $($wakeResponse.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "ERREUR de reveil: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Start-Sleep -Seconds 2

Write-Host "`nLancement des tests ($Requests requetes)..." -ForegroundColor Cyan

for ($i = 1; $i -le $Requests; $i++) {
    $start = Get-Date

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 30
        $end = Get-Date
        $duration = ($end - $start).TotalSeconds

        $results += @{
            Request = $i
            Time = $duration
            Status = $response.StatusCode
            Success = $true
        }

        $totalTime += $duration
        $successCount++
        $minTime = [Math]::Min($minTime, $duration)
        $maxTime = [Math]::Max($maxTime, $duration)

        Write-Host "Requete $i - Temps: $($duration.ToString("F2"))s - Status: $($response.StatusCode)" -ForegroundColor Green

    } catch {
        $results += @{
            Request = $i
            Time = 0
            Status = "Error"
            Success = $false
        }

        Write-Host "Requete $i - ERREUR: $($_.Exception.Message)" -ForegroundColor Red
    }

    Start-Sleep -Milliseconds 200
}

Write-Host "`n=== RESULTATS FINAUX ===" -ForegroundColor Magenta

$avgTime = if ($successCount -gt 0) { $totalTime / $successCount } else { 0 }

Write-Host "Requetes totales: $Requests" -ForegroundColor White
Write-Host "Reussites: $successCount" -ForegroundColor Green
Write-Host "Echecs: $($Requests - $successCount)" -ForegroundColor Red
Write-Host "Temps moyen: $($avgTime.ToString("F2"))s" -ForegroundColor Cyan
Write-Host "Temps minimum: $($minTime.ToString("F2"))s" -ForegroundColor Cyan
Write-Host "Temps maximum: $($maxTime.ToString("F2"))s" -ForegroundColor Cyan

if ($avgTime -lt 1) {
    Write-Host "`nPERFORMANCE EXCELLENTE (< 1s)" -ForegroundColor Green
} elseif ($avgTime -lt 3) {
    Write-Host "`nPERFORMANCE BONNE (1-3s)" -ForegroundColor Yellow
} elseif ($avgTime -lt 5) {
    Write-Host "`nPERFORMANCE MOYENNE (3-5s)" -ForegroundColor Yellow
} else {
    Write-Host "`nPERFORMANCE A AMELIORER (> 5s)" -ForegroundColor Red
}

Write-Host "`nCONSEILS D'OPTIMISATION:" -ForegroundColor Blue
Write-Host "- Utilisez la mise en cache Redis sur Render" -ForegroundColor White
Write-Host "- Optimisez les images et ressources statiques" -ForegroundColor White
Write-Host "- Activez la compression GZIP" -ForegroundColor White
Write-Host "- Utilisez un CDN pour les ressources" -ForegroundColor White