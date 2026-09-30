#!/usr/bin/env bash
# Compare the sha256 of every changed/added file (vs backup/part2-2026-09-22) at suite start with now. Run from faultlab/.
F=artifacts/product-discovery-v4-2026-09-30/fixer
shasum -a 256 -c "$F/source-sha256-at-suite-start.txt"
