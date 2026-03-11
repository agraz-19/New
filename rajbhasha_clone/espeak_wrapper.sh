#!/bin/bash
# Shift through arguments to find the text after "-t" and the output after "-o"
while [[ $# -gt 0 ]]; do
  case $1 in
    -t) text="$2"; shift; shift ;;
    -o) output="$2"; shift; shift ;;
    *) shift ;;
  esac
done
espeak "$text" -w "$output"
