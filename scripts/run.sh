#!/bin/bash

source scripts/runsetup.sh

FILE=.env
if [ -f "$FILE" ]; then
    echo "Found .env file, sourcing"
    source $FILE
fi

if [ "$OVH_USE_ASYNC" = true ] ; then
    EXE=havps-async.py
else
    EXE=havps.py
fi

if [ -f "$EXE" ]; then
    echo "Running at the root"
    python $EXE $@
else
    echo "Running in the src directory"
    python src/$EXE $@
fi
