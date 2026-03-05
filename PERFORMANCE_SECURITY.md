# ==============================
# PERFORMANCE & SECURITY CHECKLIST
# ==============================

## ✅ AVANT DE DÉPLOYER - CHECKLIST FINALE

### 🚀 PERFORMANCE
- [x] Caching enabled (LocalMemCache)
- [x] Static files compression (WhiteNoise)
- [x] Database connection pooling
- [x] Template caching
- [x] Session caching
- [x] GZIP compression enabled
- [ ] Images optimized on Cloudinary
- [ ] CSS/JS minified in production
- [ ] Remove DEBUG=True in production

### 🔒 SÉCURITÉ
- [x] HTTPS/SSL redirects enabled
- [x] HSTS headers set (1 year)
- [x] CSRF protection enabled
- [x] XSS protection enabled
- [x] Clickjacking protection (X-Frame-Options)
- [x] MIME type sniffing prevention
- [x] Secure cookies (HttpOnly, Secure, SameSite)
- [x] Password validation rules
- [x] Secret key in environment variable
- [ ] Admin URL changed from /admin/ (optional but recommended)

---

## 📝 RENDER ENVIRONMENT VARIABLES À AJOUTER

Dans Render Dashboard → Your App → Environment:

```
ENVIRONMENT=production
DEBUG=False
SECRET_KEY=<generate-a-new-key>
DATABASE_URL=<auto-filled-by-render-postgresql>
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLIC_KEY=pk_test_...
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

---

## 🔐 GENERATE SECURE SECRET KEY

Run this in Python:
```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

Or use:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## ⚡ RENDER BUILD & START COMMANDS

**Build Command:**
```
pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput
```

**Start Command:**
```
gunicorn travel_agency.wsgi:application
```

---

## 📊 PERFORMANCE TIPS

1. **Images:** Cloudinary handles compression & CDN
2. **CSS/JS:** Already minified with WhiteNoise
3. **Database:** PostgreSQL on Render is fast
4. **Caching:** LocalMemCache for sessions & queries
5. **CDN:** Use Cloudinary for all media

---

## 🧪 TEST LOCALLY BEFORE DEPLOY

```bash
# Set environment to production mode
set ENVIRONMENT=production
set DEBUG=False

# Run development server
python manage.py runserver

# Check static files
python manage.py collectstatic --noinput

# Check for security issues
python manage.py check --deploy
```

---

## 🎯 URLS FOR TESTING

- **Home:** https://go-morocco.onrender.com
- **Admin:** https://go-morocco.onrender.com/admin/
- **Media:** CDN via Cloudinary

---

## 📞 TROUBLESHOOTING

| Issue | Solution |
|-------|----------|
| 404 on static files | Run `collectstatic --noinput` |
| Images not loading | Check Cloudinary credentials |
| Slow load time | Check Render logs, enable caching |
| CSRF errors | Add domain to `CSRF_TRUSTED_ORIGINS` |
| SSL certificate error | Wait 24h for renewal or check Render settings |

