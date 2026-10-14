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

If you already have a database, run `py manage.py migrate` again after project updates. Event photos uploaded locally are stored under `media/events/`.

Guests can create an account at `/accounts/signup/` and sign in at `/accounts/login/` with their email or username. They can browse events and make bookings. Guest accounts do not have access to staff management pages.

Email/password sign-up currently does not send an email verification message. Google sign-in uses Google OAuth after credentials are configured. An email service will be needed to verify addresses and send password-reset emails.

Sign in with the superuser account to manage the lounge. Use **User accounts** in the dashboard to grant lounge roles to existing accounts. Django's `/admin/` remains available to superusers for built-in administration.

The Admin dashboard's **User accounts** page supports creating, viewing, editing, disabling, and deleting regular accounts, plus assigning roles: User, Employee, Manager, Finance, Developer, or Admin. The superuser can assign the Admin role to a trusted account. App Admin accounts can manage app users but do not become Django superusers or gain access to Django's built-in admin settings. Role access is enforced in the app: Employees can check guests in; Finance can review tickets and confirm payment; Managers can manage events, staff, tickets, and check-in; Developers can review and update support requests; Admins can use all lounge tools and manage accounts.

## Google sign-in

Google sign-in is optional. Create an OAuth 2.0 client in Google Cloud Console for a **Web application** and add this authorized redirect URI for local development:

`http://127.0.0.1:8000/accounts/google/login/callback/`

In the same PowerShell window used to start Django, set the credentials without placing them in project files:

```powershell
$env:GOOGLE_OAUTH_CLIENT_ID = "your-client-id"
$env:GOOGLE_OAUTH_CLIENT_SECRET = "your-client-secret"
python manage.py runserver
```

The Google buttons appear on sign-in and registration once both values are set. For a deployed site, add its HTTPS callback URI in Google Cloud and set the same environment variables on the host. Google’s OAuth setup and allauth’s provider configuration are described in the [allauth Google provider guide](https://docs.allauth.org/en/latest/socialaccount/providers/google.html).

## What's included

- Staff-only management dashboard with event, team and ticket summaries.
- Role-specific workspaces for Admin, Manager, Finance, Employee, and Developer, plus a guest account dashboard.
- Personal profile and password settings for every signed-in account.
- Editable profile picture uploads with a live preview and profile image storage under `media/profiles/`.
- Employee guest roster with ticket status, name search, QR scanning, manual code entry, and paid-ticket check-in.
- Event creation and published public event pages.
- Event photo uploads and a public home page gallery for all published events.
- Guest ticket reservation records and payment status tracking.
- QR ticket generation for bookings marked as paid.
- Staff check-in with camera QR scanning in supported browsers and manual code entry as a fallback.
- Team directory and Django admin screens.
- Support Center for submitting help requests, tracking status, and Developer support triage.
- In-app notifications for booking, payment, check-in, support, account, event, and team activity.

## Payment status

The reservation form currently records a booking as **Payment pending**. A staff member can confirm payment from Tickets, which activates the QR ticket. This starter does not collect card payments or send email. Connect a payment provider such as PayFast or Stripe, add its verified webhook, and configure email delivery before accepting live online payments. Never mark a booking paid based only on a browser redirect.

## Before deployment

Set `DJANGO_SECRET_KEY` to a private random value, set `DJANGO_DEBUG=0`, and set `DJANGO_ALLOWED_HOSTS` to your domain. Configure a production database, HTTPS, email, backups, and a static-file host. The default SQLite database and development secret are for local development only.
