# Tiamo's Lounge

A Django starter app for lounge operations, event listings, ticket reservations, staff records and QR based guest check-in.

## Run locally

1. Install Python 3.11 or newer.
2. From this folder, create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Create the database tables and a manager account:

   ```powershell
   py manage.py migrate
   py manage.py createsuperuser
   ```

4. Start the app with `py manage.py runserver` and visit http://127.0.0.1:8000/.

Sign in with the superuser account at `/accounts/login/`. The Django admin at `/admin/` is available for managing records and users.

## What's included

- Staff-only management dashboard with event, team and ticket summaries.
- Event creation and published public event pages.
- Guest ticket reservation records and payment status tracking.
- QR ticket generation for bookings marked as paid.
- Staff check-in with camera QR scanning in supported browsers and manual code entry as a fallback.
- Team directory and Django admin screens.

## Payment status

The reservation form currently records a booking as **Payment pending**. A staff member can confirm payment from Tickets, which activates the QR ticket. This starter does not collect card payments or send email. Connect a payment provider such as PayFast or Stripe, add its verified webhook, and configure email delivery before accepting live online payments. Never mark a booking paid based only on a browser redirect.

## Before deployment

Set `DJANGO_SECRET_KEY` to a private random value, set `DJANGO_DEBUG=0`, and set `DJANGO_ALLOWED_HOSTS` to your domain. Configure a production database, HTTPS, email, backups, and a static-file host. The default SQLite database and development secret are for local development only.
