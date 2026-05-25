#!/bin/bash
. ~/.venv/bin/activate
make | tee log.txt
make clean
read

