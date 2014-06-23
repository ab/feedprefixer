#!/bin/bash

set -eu
set -o pipefail

cd "$(dirname "$0")"

bin/python feedprefixer.py run 2>&1 | tee -a cron.log
