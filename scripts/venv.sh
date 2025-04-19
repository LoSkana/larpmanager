#!/bin/bash

# check if a virtual environment is already active
if [[ -n "$VIRTUAL_ENV" ]]; then
  return 0 2>/dev/null || exit 0
fi

# look for the first directory in the current path that contains 'venv' in its name
venv_dir=$(find . -maxdepth 1 -type d -iname "*venv*" | head -n 1)
if [[ -z "$venv_dir" ]]; then
  echo "No directory containing 'venv' found in the current directory."
  exit 1
fi

# activate the virtual environment
activate_script="$venv_dir/bin/activate"
if [[ -f "$activate_script" ]]; then
  echo "Activating virtual environment from: $activate_script"
  source "$activate_script"
else
  echo "Found '$venv_dir' but it does not contain '$activate_script'"
  exit 1
fi
