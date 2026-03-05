#!/usr/bin/env python
"""
Generate a secure SECRET_KEY for Django
Use this to update your .env file or Render environment
"""

from django.core.management.utils import get_random_secret_key

if __name__ == '__main__':
    secret_key = get_random_secret_key()
    print("\n" + "="*70)
    print("🔐 GENERATED SECURE SECRET_KEY")
    print("="*70)
    print(f"\n{secret_key}\n")
    print("="*70)
    print("INSTRUCTIONS:")
    print("="*70)
    print("1. Copy the key above")
    print("2. Add to .env file:")
    print("   SECRET_KEY=<paste-key-here>")
    print("3. OR add to Render Environment Variables:")
    print("   - Go to Settings → Environment")
    print("   - Add: SECRET_KEY = <paste-key-here>")
    print("4. Deploy!")
    print("="*70)
    print("\n⚠️  KEEP THIS KEY SECRET! Don't share it on GitHub!\n")
