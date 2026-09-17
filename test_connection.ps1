Write-Host "=========================================="
Write-Host "ERP <-> EXAM ENGINE CONNECTIVITY TEST RUN"
Write-Host "=========================================="

Write-Host "`n1) ERP health check:" -NoNewline
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
    Write-Host " ✅ ERP up ($($resp.status))" -ForegroundColor Green
} catch {
    Write-Host " ❌ ERP down ($($_))" -ForegroundColor Red
}

Write-Host "`n2) Exam health check:" -NoNewline
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get -TimeoutSec 5
    Write-Host " ✅ Exam up ($($resp.status))" -ForegroundColor Green
} catch {
    Write-Host " ❌ Exam down ($($_))" -ForegroundColor Red
}

Write-Host "`n3) Direct ERP integration endpoint test (classes):" -NoNewline
try {
    $code = curl.exe -s -o /dev/null -w "%{http_code}" -H "X-API-Key: exam-engine-dev-key" http://localhost:8000/integration/academic/classes
    if ($code -eq "200") {
        Write-Host " ✅ HTTP $code OK" -ForegroundColor Green
    } else {
        Write-Host " ❌ HTTP $code" -ForegroundColor Red
    }
} catch {
    Write-Host " ❌ Error: $_" -ForegroundColor Red
}

Write-Host "`n4) Exam -> ERP round trip via sync endpoint:" -NoNewline
try {
    $code = curl.exe -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/api/v1/integration/sync/academic
    if ($code -eq "200" -or $code -eq "202") {
        Write-Host " ✅ HTTP $code OK" -ForegroundColor Green
    } else {
        Write-Host " ❌ HTTP $code" -ForegroundColor Red
    }
} catch {
    Write-Host " ❌ Error: $_" -ForegroundColor Red
}

Write-Host "`n5) Latency test - 5 sequential calls timing:"
for ($i = 1; $i -le 5; $i++) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $code = curl.exe -s -o /dev/null -w "%{http_code}" -H "X-API-Key: exam-engine-dev-key" http://localhost:8000/integration/academic/classes
    $sw.Stop()
    $ms = $sw.ElapsedMilliseconds
    Write-Host "   call ${i}: $ms ms (HTTP $code)"
}
Write-Host "`n=========================================="
