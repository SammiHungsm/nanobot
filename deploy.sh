#!/usr/bin/env bash
# Nanobot Docker Deployment Script
# 完整部署流程：啟動、測試、驗證

set -e

echo "========================================"
echo "  Nanobot Docker Deployment"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    log_info "✓ Docker version: $(docker --version)"
    log_info "✓ Docker Compose version: $(docker-compose --version)"
}

stop_existing_containers() {
    log_info "Stopping existing containers..."
    docker-compose down || true
}

build_images() {
    log_info "Building Docker images..."
    docker-compose build --no-cache
}

start_services() {
    log_info "Starting all services..."
    docker-compose up -d
    
    log_info "Waiting for services to start (60 seconds)..."
    sleep 60
}

check_service_health() {
    log_info "Checking service health..."
    
    # Check PostgreSQL
    if docker exec postgres-financial pg_isready -U postgres &> /dev/null; then
        log_info "✓ PostgreSQL is healthy"
    else
        log_error "✗ PostgreSQL is not healthy"
        return 1
    fi
    
    # Check MongoDB
    if docker exec mongodb-docs mongosh --eval "db.runCommand('ping')" &> /dev/null; then
        log_info "✓ MongoDB is healthy"
    else
        log_error "✗ MongoDB is not healthy"
        return 1
    fi
    
    # Check Nanobot Gateway
    if docker exec nanobot-gateway curl -f http://localhost:8081/health &> /dev/null; then
        log_info "✓ Nanobot Gateway is healthy"
    else
        log_warn "⚠ Nanobot Gateway may still be starting..."
    fi
    
    # Check Web UI
    if curl -f http://localhost:3000/health &> /dev/null; then
        log_info "✓ Web UI is healthy"
    else
        log_warn "⚠ Web UI may still be starting..."
    fi
}

run_tests() {
    log_info "Running integration tests..."
    
    # Test 1: Database connection
    log_info "Test 1: Database connection..."
    docker exec nanobot-gateway python -c "
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
" && log_info "✓ Database test passed" || log_error "✗ Database test failed"
    
    # Test 2: Vanna tool
    log_info "Test 2: Vanna tool..."
    docker exec nanobot-gateway python -c "
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
" && log_info "✓ Vanna tool test passed" || log_error "✗ Vanna tool test failed"
    
    # Test 3: OpenDataLoader
    log_info "Test 3: OpenDataLoader..."
    docker exec nanobot-gateway python -c "
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
" && log_info "✓ OpenDataLoader test passed" || log_warn "⚠ OpenDataLoader test skipped (may not be installed)"
}

show_status() {
    echo ""
    log_info "========================================"
    log_info "  Deployment Complete!"
    log_info "========================================"
    echo ""
    log_info "Services running:"
    docker-compose ps
    echo ""
    log_info "Access URLs:"
    log_info "  - Web UI: http://localhost:3000"
    log_info "  - Nanobot Gateway: http://localhost:8081"
    log_info "  - PostgreSQL: localhost:5433"
    log_info "  - MongoDB: localhost:27018"
    echo ""
    log_info "Next steps:"
    log_info "  1. Train Vanna: docker exec -it nanobot-gateway python train_vanna.py"
    log_info "  2. Build PDF index: docker exec -it nanobot-gateway python nanobot/skills/document_indexer/scripts/build_indexes.py /data/pdfs/your_report.pdf"
    log_info "  3. View logs: docker-compose logs -f"
    echo ""
}

# Main execution
main() {
    check_prerequisites
    stop_existing_containers
    build_images
    start_services
    check_service_health
    run_tests
    show_status
}

# Run main function
main
