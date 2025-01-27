#!/bin/bash

# Enable strict mode for error handling
set -euo pipefail

# Output file
output_file="/usr/src/dumps/utxos.csv"

# Run the dumper binary
/usr/bin/dumper > "$output_file"

# Wait indefinitely after execution
tail -f /dev/null