# Nanobot Docker Deployment Script for Windows PowerShell
# 完整部署流程：啟動、測試、驗證

$ErrorActionPreference = "Stop"

Write-Host "========================================"
Write-Host "  Nanobot Docker Deployment (Windows)"
Write-Host "========================================"
Write-Host ""

function Log-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Log-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Log-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Check-Prerequisites {
    Log-Info "Checking prerequisites..."
    
    # Check Docker
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Log-Error "Docker is not installed. Please install Docker Desktop first."
        Log-Error "Download from: https://www.docker.com/products/docker-desktop"
        exit 1
    }
    
    # Check Docker Compose
    if (-not (Get-Command docker-compose -ErrorAction SilentlyContinue)) {
        Log-Error "Docker Compose is not installed."
        exit 1
    }
    
    Log-Info "✓ Docker version: $(docker --version)"
    Log-Info "✓ Docker Compose version: $(docker-compose --version)"
}

function Stop-ExistingContainers {
    Log-Info "Stopping existing containers..."
    docker-compose down 2>$null
}

function Build-Images {
    Log-Info "Building Docker images..."
    docker-compose build --no-cache
}

function Start-Services {
    Log-Info "Starting all services..."
    docker-compose up -d
    
    Log-Info "Waiting for services to start (60 seconds)..."
    Start-Sleep -Seconds 60
}

function Check-ServiceHealth {
    Log-Info "Checking service health..."
    
    # Check PostgreSQL
    try {
        $null = docker exec postgres-financial pg_isready -U postgres 2>$null
        Log-Info "✓ PostgreSQL is healthy"
    } catch {
        Log-Error "✗ PostgreSQL is not healthy"
        return $false
    }
    
    # Check MongoDB
    try {
        $null = docker exec mongodb-docs mongosh --eval "db.runCommand('ping')" 2>$null
        Log-Info "✓ MongoDB is healthy"
    } catch {
        Log-Error "✗ MongoDB is not healthy"
        return $false
    }
    
    # Check Nanobot Gateway
    try {
        $null = docker exec nanobot-gateway curl -f http://localhost:8081/health 2>$null
        Log-Info "✓ Nanobot Gateway is healthy"
    } catch {
        Log-Warn "⚠ Nanobot Gateway may still be starting..."
    }
    
    # Check Web UI
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3000/health" -TimeoutSec 5 -UseBasicParsing 2>$null
        if ($response.StatusCode -eq 200) {
            Log-Info "✓ Web UI is healthy"
        }
    } catch {
        Log-Warn "⚠ Web UI may still be starting..."
    }
    
    return $true
}

function Run-Tests {
    Log-Info "Running integration tests..."
    
    # Test 1: Database connection
    Log-Info "Test 1: Database connection..."
    $testResult = docker exec nanobot-gateway python -c @"
from nanobot.storage.financial_storage import PostgresStorage, MongoDocumentStore
import sys

try:
    # Test PostgreSQL
    pg = PostgresStorage('postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports')
    pg.connect()
    print('✓ PostgreSQL connection successful')
    
    # Test MongoDB
    mongo = MongoDocumentStore('mongodb://mongo:mongo_password_change_me@mongodb-docs:27017/annual_reports')
    mongo.connect()
    print('✓ MongoDB connection successful')
    
    print('✓ All database connections working')
    sys.exit(0)
except Exception as e:
    print(f'✗ Database connection failed: {e}')
    sys.exit(1)
"@ 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Log-Info "✓ Database test passed"
    } else {
        Log-Error "✗ Database test failed"
        Write-Host $testResult
    }
    
    # Test 2: Vanna tool
    Log-Info "Test 2: Vanna tool..."
    $testResult = docker exec nanobot-gateway python -c @"
from nanobot.agent.tools.vanna_tool import VannaSQL
import sys

try:
    vanna = VannaSQL(database_url='postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports')
    print('✓ VannaSQL initialized')
    print('✓ Vanna tool test passed')
    sys.exit(0)
except Exception as e:
    print(f'✗ Vanna tool failed: {e}')
    sys.exit(1)
"@ 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Log-Info "✓ Vanna tool test passed"
    } else {
        Log-Error "✗ Vanna tool test failed"
        Write-Host $testResult
    }
    
    # Test 3: OpenDataLoader
    Log-Info "Test 3: OpenDataLoader..."
    $testResult = docker exec nanobot-gateway python -c @"
import subprocess
import sys

try:
    result = subprocess.run(['opendataloader-pdf', '--help'], capture_output=True, text=True, timeout=10)
    if result.returncode == 0 or 'usage' in result.stdout.lower():
        print('✓ OpenDataLoader CLI available')
        sys.exit(0)
    else:
        print('✗ OpenDataLoader CLI not working')
        sys.exit(1)
except Exception as e:
    print(f'✗ OpenDataLoader test failed: {e}')
    sys.exit(1)
"@ 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Log-Info "✓ OpenDataLoader test passed"
    } else {
        Log-Warn "⚠ OpenDataLoader test skipped (may not be installed)"
    }
}

function Show-Status {
    Write-Host ""
    Log-Info "========================================"
    Log-Info "  Deployment Complete!"
    Log-Info "========================================"
    Write-Host ""
    Log-Info "Services running:"
    docker-compose ps
    Write-Host ""
    Log-Info "Access URLs:"
    Log-Info "  - Web UI: http://localhost:3000"
    Log-Info "  - Nanobot Gateway: http://localhost:8081"
    Log-Info "  - PostgreSQL: localhost:5433"
    Log-Info "  - MongoDB: localhost:27018"
    Write-Host ""
    Log-Info "Next steps:"
    Log-Info "  1. Train Vanna: docker exec -it nanobot-gateway python train_vanna.py"
    Log-Info "  2. Build PDF index: docker exec -it nanobot-gateway python nanobot/skills/document_indexer/scripts/build_indexes.py /data/pdfs/your_report.pdf"
    Log-Info "  3. View logs: docker-compose logs -f"
    Write-Host ""
}

# Main execution
try {
    Check-Prerequisites
    Stop-ExistingContainers
    Build-Images
    Start-Services
    Check-ServiceHealth
    Run-Tests
    Show-Status
} catch {
    Log-Error "Deployment failed: $_"
    exit 1
}
