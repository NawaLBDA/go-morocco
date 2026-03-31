# Robocall System Setup Guide

## 🎯 Overview
This system enables automated voice calls for booking verification on `maroc.local` only. When a booking is validated, the user can click a "Call for verification" button that triggers an automatic call workflow using Twilio.

## 🚀 Quick Start

### 1. Get Twilio Credentials
1. Sign up at [twilio.com](https://twilio.com)
2. Get your credentials:
   - **Account SID**
   - **Auth Token**
   - **Phone Number** (from-number for Twilio)
3. Verify the two Moroccan phone numbers:
   - Primary: `+212644061453`
   - Secondary: `+212643092852`

### 2. Configure Environment Variables
Add to your `.env` file:
```
TWILIO_ACCOUNT_SID=AC1234567890abcdefg
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_FROM_NUMBER=+15551234567
ROBOCALL_PRIMARY_NUMBER=+212644061453
ROBOCALL_SECONDARY_NUMBER=+212643092852
```

### 3. Install Dependencies
```bash
pip install twilio
# Already added to requirements.txt
```

### 4. Deploy to Render
1. Add environment variables in Render dashboard
2. Push code to git
3. Render auto-deploys

## 📋 How It Works

### Workflow
```
User books tour → Booking validated → User sees "Call for verification" button (Morocco only)
         ↓
   User clicks button
         ↓
   Django calls /api/robo-call/<booking_id>/
         ↓
   Twilio initiates call to PRIMARY number
         ↓
   If no answer (60s timeout) → Twilio calls SECONDARY number
         ↓
   If still no answer → Voice message: "We'll retry soon"
```

### Button Visibility
- **Only for Morocco**: `if country == 'morocco'`
- **Only after booking validated**: `if reservation.status == 'booked'`
- **JavaScript handler**: Sends POST to `/api/robo-call/<booking_id>/`

## 🔧 Endpoints

### API
- **POST** `/api/robo-call/<booking_id>/`
  - Triggers voice call
  - Returns JSON with call SID or error
  - User must own reservation

### TwiML Webhooks (Called by Twilio)
- `/twiml/call-first/<booking_id>/` - First dial attempt
- `/twiml/call-fallback/<booking_id>/` - Fallback to secondary number
- `/twiml/call-complete/<booking_id>/` - Final status handling

## 🎙️ Voice Messages
- **First attempt**: Dials +212644061453 (60s timeout)
- **If failed**: "Aucun réponse sur la première ligne. Transfert vers le second numéro."
- **Second attempt**: Dials +212643092852 (60s timeout)
- **If successful**: "Appel effectué. Merci, l'agent prend la suite."
- **If failed**: "Nous n'avons pas pu joindre le numéro. Merci, nous réessayons bientôt."

## 🧪 Testing (Local)

### Mock Twilio (Dev Mode)
Option 1: Use Twilio Trial Account
- Free $15 trial credit
- Use your verified numbers
- Full webhook support

Option 2: Mock Twilio API (for dev)
```python
# In views.py, add mock for dev:
if settings.DEBUG and not settings.TWILIO_ACCOUNT_SID:
    return JsonResponse({'message': 'MOCK: Call would be initiated'})
```

### Test Locally with ngrok
```bash
# 1. Start ngrok
ngrok http 8000

# 2. Update TWILIO_FROM_NUMBER and webhooks in Twilio console
# Set webhook URLs to: https://your-ngrok-url.ngrok.io/twiml/call-first/...

# 3. Test button in browser
```

## 🌍 Country Detection
- **maroc.local** → country='morocco' → Button visible
- **ireland.local** → country='ireland' → Button NOT visible
- Logic in [apps/core/context_processors.py](apps/core/context_processors.py) via `get_country_from_site()`

## 📱 Production Checklist
- [ ] Twilio credentials set in Render environment
- [ ] CSRF exemption on TwiML endpoints (already done with `@csrf_exempt`)
- [ ] Webhook URLs updated in Twilio console to production domain
- [ ] Test booking on production with real Twilio trial
- [ ] Monitor call logs in Twilio dashboard

## ⚠️ Legal / Compliance
- **Morocco**: Verify compliance with local telecom regulations for automated calls
- **DNC (Do Not Call)**: Add opt-out mechanism if required
- **User Consent**: Ensure user explicitly clicked button (already enforced)

## 🐛 Troubleshooting

### Call not initiating
1. Check Twilio credentials in `.env`
2. Verify TWILIO_ACCOUNT_SID is not empty: `python manage.py shell`
3. Check browser console for fetch errors
4. Verify booking is `status='booked'`

### Twilio returns 403
1. Ensure CSRF token is sent with POST request (JS handles this)
2. Add webhook URL to Twilio console safe list

### No fallback to second number
1. Check `DialCallStatus` in webhook request
2. Verify second number format: `+212643092852`

## 📖 Files Modified
- `travel_agency/settings.py` - Added Twilio config
- `apps/core/views.py` - Added robocall handlers and TwiML endpoints
- `apps/core/urls.py` - Added API and TwiML routes
- `templates/booking.html` - Added "Call" button + JS handler
- `requirements.txt` - Added twilio package

## 🔐 Security Notes
- Only authenticated users can trigger calls
- User must own the reservation
- Booking must be validated (status='booked')
- Country filtering prevents calls for Ireland
- TwiML endpoints need `@csrf_exempt` (POST from Twilio)

## 📞 Support
For Twilio issues: [https://www.twilio.com/console](https://www.twilio.com/console)
Check [Twilio Docs](https://www.twilio.com/docs/voice) for voice API details.
