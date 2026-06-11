#!/bin/bash
# Shift through arguments to find the text after "-t" and the output after "-o"
while [[ $# -gt 0 ]]; do
  case $1 in
    -t) text="$2"; shift; shift ;;
    -o) output="$2"; shift; shift ;;
    *) shift ;;
  esac
done

spaced_text=$(echo "$text" | sed 's/./& /g')
espeak -s 120 -g 80 "$spaced_text" -w "$output"
