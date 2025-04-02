#!/bin/bash

# Terminal colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Debug flag
DEBUG=false
[[ "$1" == "--debug" ]] && DEBUG=true && echo -e "${BLUE}${BOLD}Debug mode enabled${NC}"

# Print banner
echo -e "\n${BOLD}NAVICAST STARTUP${NC}\n"

# Make sure Postgres is running
echo -e "${BOLD}Checking PostgreSQL...${NC}"
if pg_isready -h localhost -p 5432 | grep -q "accepting connections"; then
    echo -e "  ${GREEN}✓ PostgreSQL is running${NC}"
else
    echo -e "  ${RED}✗ PostgreSQL is not running${NC}"
    echo -e "  Start PostgreSQL first, then try again."
    exit 1
fi

# Function to start a service
start_service() {
    local name=$1
    local script=$2
    local log=$3
    
    echo -e "${BOLD}Starting ${name}...${NC}"
    
    # Check if already running
    if pgrep -f "$script" > /dev/null; then
        echo -e "  ${YELLOW}⚠ ${name} is already running${NC}"
        return 0
    fi
    
    # Show command in debug mode
    [[ "$DEBUG" = true ]] && echo -e "  ${BLUE}Debug: Running 'python $script > logs/$log 2>&1 &'${NC}"
    
    # Start the service
    python "$script" > "logs/$log" 2>&1 &
    local pid=$!
    
    # Give it a moment to start
    sleep 0.5
    if ps -p $pid > /dev/null; then
        echo -e "  ${GREEN}✓ ${name} started (PID: $pid)${NC}"
        return 0
    else
        echo -e "  ${RED}✗ Failed to start ${name}${NC}"
        echo -e "  ${YELLOW}Check logs/$log for details${NC}"
        return 1
    fi
}

# Handle Ctrl+C gracefully
cleanup() {
    echo -e "\n${YELLOW}${BOLD}Stopping NAVICAST services...${NC}"
    pkill -f "mqtt_client.py|prediction_service.py|api_server.py"
    echo -e "${GREEN}${BOLD}All services stopped${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Fire up the services
echo -e "\n${BOLD}Starting services:${NC}"
start_service "MQTT client" "mqtt_client.py" "mqtt_output.log" || { cleanup; exit 1; }

# Wait a bit for data to come in
echo -e "${BLUE}Waiting for initial data ingestion...${NC}"
sleep 5

# Start the rest of the services
start_service "Prediction service" "prediction_service.py" "prediction_output.log" || { cleanup; exit 1; }
start_service "API server" "api_server.py" "api_output.log" || { cleanup; exit 1; }

# Show final status message
echo -e "\n${BOLD}NAVICAST SYSTEM IS RUNNING${NC}"
echo -e "${BOLD}Web interface:${NC} ${YELLOW}http://localhost:8000${NC}"
echo -e "${BOLD}Log files:${NC} ${YELLOW}logs/mqtt_output.log, logs/prediction_output.log, logs/api_output.log${NC}"
echo -e "\n${BOLD}Press Ctrl+C to stop all services${NC}\n"

# Keep the script running until Ctrl+C
while true; do sleep 1; done