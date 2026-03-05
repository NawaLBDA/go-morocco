#!/bin/bash

# ========================================
# Deployment Quick Start Script
# Linux/Mac Version
# ========================================

echo ""
echo "========================================"
echo "  🚀 TRAVEL AGENCY - DEPLOYMENT SETUP"
echo "========================================"
echo ""

# 1. Generate SECRET_KEY
echo "[1/4] Generating new SECRET_KEY..."
python3 generate_secret_key.py
echo ""

# 2. Run security check
echo "[2/4] Running security check..."
python3 check_security.py
echo ""

# 3. Collect static files
echo "[3/4] Collecting static files..."
python3 manage.py collectstatic --noinput
echo ""

# 4. Info to deploy
echo "[4/4] Ready to deploy!"
echo ""
echo "========================================"
echo "  ✅ SETUP COMPLETE"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Copy your new SECRET_KEY"
echo "2. Push to GitHub: git push origin main"
echo "3. Go to https://render.com"
echo "4. Create Web Service and add variables"
echo ""
echo "Documentation:"
echo "- DEPLOY_NOW.md (Quick start)"
echo "- DEPLOYMENT_GUIDE.md (Full guide)"
echo "- PERFORMANCE_SECURITY.md (Checklist)"
echo ""
echo "========================================"
echo ""
