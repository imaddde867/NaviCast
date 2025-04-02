# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# Debug mode
DEBUG=false
[[ "$1" == "--debug" ]] && DEBUG=true && echo -e "${BLUE}${BOLD}Debug mode enabled${NC}"

echo -e "\n${BOLD}===============================================${NC}"
echo -e "${GREEN}${BOLD}           NAVICAST  STARTUP           ${NC}"
echo -e "${BOLD}===============================================${NC}\n"

# Check PostgreSQL
echo -e "${BOLD}Checking PostgreSQL...${NC}"
if pg_isready -h localhost -p 5432 | grep -q "accepting connections"; then
    echo -e "  ${GREEN}✓ PostgreSQL is running${NC}"
else
    echo -e "  ${RED}✗ PostgreSQL is not running${NC}"
    echo -e "  Please start PostgreSQL and try again."
    exit 1
fi

# Start a service
start_service() {
    local name=$1
    local script=$2
    local log=$3
    
    echo -e "${BOLD}Starting ${name}...${NC}"
    
    if pgrep -f "$script" > /dev/null; then
        echo -e "  ${YELLOW}⚠ ${name} is already running${NC}"
        return 0
    fi
    
    [[ "$DEBUG" = true ]] && echo -e "  ${BLUE}Debug: Running 'python $script > logs/$log 2>&1 &'${NC}"
    
    python "$script" > "logs/$log" 2>&1 &
    local pid=$!
    
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

# Cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}${BOLD}Stopping NAVICAST services...${NC}"
    pkill -f "mqtt_client.py|prediction_service.py|api_server.py"
    echo -e "${GREEN}${BOLD}All services stopped${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start services
echo -e "\n${BOLD}Starting services:${NC}"
start_service "MQTT client" "mqtt_client.py" "mqtt_output.log" || { cleanup; exit 1; }

echo -e "${BLUE}Waiting for initial data ingestion...${NC}"
sleep 5

start_service "Prediction service" "prediction_service.py" "prediction_output.log" || { cleanup; exit 1; }
start_service "API server" "api_server.py" "api_output.log" || { cleanup; exit 1; }

# Final status
echo -e "\n${BOLD}===============================================${NC}"
echo -e "${GREEN}${BOLD}       NAVICAST SYSTEM IS RUNNING       ${NC}"
echo -e "${BOLD}===============================================${NC}"
echo -e "${BOLD}Web interface:${NC} ${YELLOW}http://localhost:8000${NC}"
echo -e "${BOLD}Log files:${NC} ${YELLOW}logs/mqtt_output.log, logs/prediction_output.log, logs/api_output.log${NC}"
echo -e "\n${BOLD}Press Ctrl+C to stop all services${NC}\n"

# Keep script running
while true; do sleep 1; done