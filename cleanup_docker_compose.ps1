# Docker Compose 清理脚本
# 只保留 nanobot/docker-compose.yml

Write-Host "=== Docker Compose 清理脚本 ===" -ForegroundColor Cyan
Write-Host ""

# 检查文件是否存在
$filesToDelete = @(
    "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\docker-compose.yml",
    "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\docker-compose.gpu.yml"
)

$dirsToDelete = @(
    "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\vanna"
)

Write-Host "将要删除的文件：" -ForegroundColor Yellow
foreach ($file in $filesToDelete) {
    if (Test-Path $file) {
        Write-Host "  [FILE] $file" -ForegroundColor Red
    }
}

Write-Host "将要删除的目录：" -ForegroundColor Yellow
foreach ($dir in $dirsToDelete) {
    if (Test-Path $dir) {
        Write-Host "  [DIR]  $dir" -ForegroundColor Red
    }
}

Write-Host ""
$confirm = Read-Host "确认删除？(Y/N)"

if ($confirm -eq "Y" -or $confirm -eq "y") {
    # 删除文件
    foreach ($file in $filesToDelete) {
        if (Test-Path $file) {
            Remove-Item $file -Force
            Write-Host "[OK] 已删除: $file" -ForegroundColor Green
        }
    }

    # 删除目录
    foreach ($dir in $dirsToDelete) {
        if (Test-Path $dir) {
            Remove-Item $dir -Recurse -Force
            Write-Host "[OK] 已删除: $dir" -ForegroundColor Green
        }
    }

    Write-Host ""
    Write-Host "=== 清理完成 ===" -ForegroundColor Cyan
    Write-Host "保留的文件：" -ForegroundColor Yellow
    Write-Host "  [OK] nanobot\docker-compose.yml" -ForegroundColor Green

    # 询问是否删除 LightRAG
    Write-Host ""
    $deleteLightRAG = Read-Host "是否也删除 LightRAG 目录？(Y/N)"
    if ($deleteLightRAG -eq "Y" -or $deleteLightRAG -eq "y") {
        $lightragDir = "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG"
        if (Test-Path $lightragDir) {
            Remove-Item $lightragDir -Recurse -Force
            Write-Host "[OK] 已删除 LightRAG 目录" -ForegroundColor Green
        }
    }
} else {
    Write-Host "已取消删除" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "下一步：" -ForegroundColor Cyan
Write-Host "  cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot"
Write-Host "  docker compose up --build"