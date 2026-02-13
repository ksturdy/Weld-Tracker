#!/usr/bin/env bash
set -o errexit

# Install system dependencies for OCR and PDF processing
apt-get update && apt-get install -y tesseract-ocr poppler-utils

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
