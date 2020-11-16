#!/bin/bash

source scripts/runsetup.sh

FILE=.env
if [ -f "$FILE" ]; then
    echo "Found .env file, sourcing"
    source $FILE
fi

if [ -f "havps.py" ]; then
    echo "Running at the root"
    python havps.py $@
else
    echo "Running in the src directory"
    python src/havps.py $@
fi
