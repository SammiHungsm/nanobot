# Test PDF Upload Script
$filePath = "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\data\uploads\stock_00001_2023.pdf"
$fileName = "stock_00001_2023.pdf"

Write-Host "Uploading PDF: $fileName"
Write-Host ""

# Copy test file if not exists
if (-not (Test-Path $filePath)) {
    Write-Host "Creating test PDF from uploads folder..."
    $sourcePdf = docker exec nanobot-webui ls /app/uploads/*.pdf | Select-Object -First 1
    if ($sourcePdf) {
        docker cp "nanobot-webui:$sourcePdf" $filePath
    }
}

# Upload via API
$form = @{
    files = Get-Item -Path $filePath
    doc_type = "annual_report"
}

try {
    $response = Invoke-RestMethod -Uri "http://localhost:3000/api/upload?doc_type=annual_report" -Method Post -Form $form
    Write-Host "Upload Response:"
    $response | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Upload Error: $_"
}

# Wait and check logs
Write-Host ""
Write-Host "Checking processing logs..."
Start-Sleep 5
docker logs nanobot-webui 2>&1 | Select-Object -Last 30