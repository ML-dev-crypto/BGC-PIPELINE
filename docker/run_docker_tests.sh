#!/bin/bash
# Automated Docker-based testing for BGC-QDR pipeline

set -e

echo "=========================================="
echo "BGC-QDR Docker Testing Suite"
echo "=========================================="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Function to run a specific test
run_test() {
    local service=$1
    local description=$2
    
    echo "=========================================="
    echo "Running: $description"
    echo "=========================================="
    docker-compose up --build $service
    echo ""
}

# Parse command line arguments
case "${1:-all}" in
    deepbgc)
        run_test deepbgc "DeepBGC Comparison"
        ;;
    antismash)
        run_test antismash "antiSMASH Comparison"
        ;;
    bgcqdr)
        run_test bgc-qdr-test "BGC-QDR Pipeline Tests"
        ;;
    all)
        echo "Running all tests..."
        echo ""
        run_test bgc-qdr-test "BGC-QDR Pipeline Tests"
        run_test deepbgc "DeepBGC Comparison"
        echo ""
        echo "=========================================="
        echo "All tests complete!"
        echo "=========================================="
        echo ""
        echo "Results available in:"
        echo "  - benchmark_results/deepbgc_*/"
        echo "  - benchmark_results/benchmark_report.txt"
        ;;
    clean)
        echo "Cleaning up Docker containers and images..."
        docker-compose down --rmi all -v
        echo "✅ Cleanup complete"
        ;;
    *)
        echo "Usage: $0 {deepbgc|antismash|bgcqdr|all|clean}"
        echo ""
        echo "Options:"
        echo "  deepbgc    - Run DeepBGC comparison only"
        echo "  antismash  - Run antiSMASH comparison only (requires more resources)"
        echo "  bgcqdr     - Run BGC-QDR pipeline tests only"
        echo "  all        - Run all tests (default)"
        echo "  clean      - Remove all Docker containers and images"
        exit 1
        ;;
esac
