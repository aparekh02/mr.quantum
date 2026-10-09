#!/usr/bin/env bash
# Sprint 3 demo: drive upstream routines over HTTP with curl and watch the stream.
# Needs a running API (make serve). Override the address with API=http://host:port.
set -euo pipefail
API="${API:-http://127.0.0.1:8765}"
JSON='content-type: application/json'
py() { python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }

sid=$(curl -sf -X POST "$API/sessions" -H "$JSON" -d '{"device": "dqd_with_sensor"}' | py 'print(d["id"])')
echo "session $sid"

run() {  # run <label> <json body>; waits for completion
  status=$(curl -sf -X POST "$API/sessions/$sid/runs?wait=true" -H "$JSON" -d "$2" | py 'print(d["status"])')
  echo "$1: $status"
  [ "$status" = "succeeded" ]
}

SWEEP='"measure_electrode": "OUT_B", "bias_gate": "IN_B", "bias_voltage": 0.001, "charge_carrier_type": "hole", "step_size": 0.01, "group": "side_B"'
run side_B/noise_floor_measurement '{"routine": "noise_floor_measurement", "parameters": {"measure_electrode": "OUT_B", "group": "side_B"}}'
run side_B/leakage_test '{"routine": "leakage_test", "parameters": {"leakage_threshold_resistance": 50000000, "group": "side_B"}}'
run side_B/global_accumulation "{\"routine\": \"global_accumulation\", \"parameters\": {$SWEEP}}"
run side_B/reservoir_characterization "{\"routine\": \"reservoir_characterization\", \"parameters\": {$SWEEP}}"
run side_B/finger_gate_characterization "{\"routine\": \"finger_gate_characterization\", \"parameters\": {$SWEEP}}"

cursor=$(curl -sf "$API/sessions/$sid/events" | py 'print(d[-1]["seq"] if d else 0)')
run_id=$(curl -sf -X POST "$API/sessions/$sid/runs" -H "$JSON" -d '{
  "routine": "find_sensor_peak",
  "parameters": {"peak_spacing": 0.02, "sensor_group_name": "side_B",
                 "sensor_plunger_gate": "PB", "measure_electrode": "OUT_B",
                 "bias_gate": "IN_B", "bias_voltage": 0.001, "settling_time_s": 0}}' | py 'print(d["id"])')

# Watch the live stream (server-sent events) until the run ends.
curl -sN "$API/sessions/$sid/events/stream?after=$cursor&until=run_finished" \
  | awk '/^event: /{n[$2]++} END {printf "streamed:"; for (k in n) printf " %s=%d", k, n[k]; print ""}'

curl -sf "$API/sessions/$sid/runs/$run_id?wait=true" \
  | py 'print(d["routine"] + ": " + d["status"]); print(json.dumps({k: d["result"][k] for k in ("best_peak_voltage", "best_peak_max_gradient_voltage", "narrowed_sensor_plunger_range")}, indent=2))'
