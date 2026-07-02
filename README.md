to run:

git clone https://github.com/ikokojin/ncst-face-detection-system.git 

cd ncst-face-detection-system

cp .env.example .env

python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

## Gmail setup (required for OTP emails)

1. Enable 2-Step Verification on `paullacuesta732@gmail.com`
2. Create a Gmail App Password: https://myaccount.google.com/apppasswords
3. Add it to `.env`:
   ```
   SMTP_PASSWORD=your-16-character-app-password
   ```
4. Restart the server after updating `.env`

Without `SMTP_PASSWORD`, OTP codes are printed to the server console only (dev mode).

## Default main admin

- Email: `paullacuesta732@gmail.com`
- Password: `NCST 2026`

## Auth pages

- Login: `/login`
- Forgot password (OTP to user's email): `/forgot-password`
- Create admin account (approval code to main admin): `/register`

python run.py
