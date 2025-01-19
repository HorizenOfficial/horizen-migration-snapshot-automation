#!/bin/bash

# Enable strict mode for error handling
set -euo pipefail

# Output file
OUTPUT_FILE="/usr/bin/utxos.csv"

# Run the dumper binary
/usr/bin/dumper > "$OUTPUT_FILE"

# Wait indefinitely after execution
tail -f /dev/null