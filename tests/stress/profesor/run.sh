set -eu
RATE=50
DURATION=30s
TIMEOUT=30s
TARGETS=/stress/profesor/test_carga.txt
BIN_OUTPUT=/stress/results/profesor-vegeta.bin
JSON_OUTPUT=/stress/results/profesor-vegeta.json
PLOT_OUTPUT=/stress/results/profesor-vegeta.html
vegeta attack -rate="${RATE}" -duration="${DURATION}" -timeout="${TIMEOUT}" -targets="${TARGETS}" > "${BIN_OUTPUT}"
vegeta report < "${BIN_OUTPUT}"
vegeta report -type=json < "${BIN_OUTPUT}" > "${JSON_OUTPUT}"
vegeta plot < "${BIN_OUTPUT}" > "${PLOT_OUTPUT}"
