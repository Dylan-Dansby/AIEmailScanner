# Job Email Scanner Agent

A small desktop app that watches your inbox for the emails you can't afford to miss: **job interview invitations, job offers, and acceptance letters**. It checks your unread mail 2-3 times a day, uses OpenAI to decide which messages matter, and shows you a short report with the company, category, and a summary.

Everything lives in a single file (`Email_Scanner.py`) with a simple tkinter interface. Nothing is hardcoded, so anyone can use it with their own email and OpenAI key.

## Features

- Scans unread emails on a schedule you choose (2-3 times per day)
- Countdown timer showing when the next scan runs
- "Scan now" button for an instant check
- Reports only matches (interview, offer, or acceptance) and ignores everything else
- Read-only access to your mailbox: your emails are **not** marked as read, moved, or deleted
- Your password and API key are kept in memory only and never saved to disk

## Requirements

- Python 3.8 or newer
- An email account with IMAP access (Gmail by default)
- A Gmail **app password** (see below) or the equivalent for your provider
- An OpenAI API key

Install the one dependency:

```bash
pip install openai
```

tkinter ships with Python on Windows and macOS. On some Linux distributions you may need `sudo apt install python3-tk`.

## Getting your credentials

### Gmail app password

Gmail will not accept your normal password for this app. You need an app password:

1. Turn on **2-Step Verification** for your Google account.
2. Go to **Google Account → Security → App passwords**.
3. Create a new app password and copy the 16-character code (spaces are fine).

### OpenAI API key

1. Sign in at [platform.openai.com](https://platform.openai.com).
2. Go to **API keys** and create a new key.
3. Copy it right away; you won't be able to view it again.

## Running the app

Start it with:

```bash
python GUI.py
```

Fill in the **Settings** fields, then click **Start schedule** (or **Scan now** for an immediate check):

| Field | What to enter |
|---|---|
| IMAP server | `imap.gmail.com` (default) or your provider's IMAP server |
| Email address | The inbox to scan |
| App password | Your Gmail app password |
| OpenAI API key | Your OpenAI key (starts with `sk-`) |
| Scan times (24h) | 2 or 3 times in `HH:MM` format, e.g. `08:00, 13:00, 19:00` |

### Optional: skip the typing

You can supply values as command-line arguments:

```bash
python GUI.py --email you@gmail.com --password "abcd efgh ijkl mnop" --api-key sk-...
```

Available arguments: `--email`, `--password`, `--api-key`, `--host`, `--times`.

Or set environment variables:

| Variable | Value |
|---|---|
| `EMAIL_USER` | Your email address |
| `EMAIL_APP_PASSWORD` | Your app password |
| `OPENAI_API_KEY` | Your OpenAI key |

If more than one source is used, the priority is: command-line arguments, then environment variables, then saved settings, then defaults. When all four required values are supplied up front, the schedule starts automatically.

### Optional: double-click launcher (Windows)

Create a `run_scanner.bat` in the same folder:

```bat
@echo off
cd /d "C:\path\to\your\folder"
python GUI.py
pause
```

Don't put your password or API key in the .bat file. Type them into the app or use environment variables instead.

## How it works

1. At each scheduled time, the app connects to your mailbox over IMAP (SSL) in read-only mode.
2. It pulls up to the **25 most recent unread emails** and trims each body to about 1,500 characters.
3. Each email is sent to OpenAI (`gpt-4o-mini`) with a prompt asking whether it is an interview invitation, job offer, or acceptance letter.
4. Matches are shown in the **Latest report** box with the company, category, sender, subject, and a short summary.

You can change the model, email limit, and body length at the top of `GUI.py` (`MODEL`, `MAX_EMAILS`, `BODY_CHARS`).

## Privacy and security

- Your **password and API key are never written to disk**. Only your server, email address, and scan times are saved, in `settings.json` next to the script.
- The text of your unread emails (subject and the start of the body) is sent to OpenAI for analysis. Don't use this app if you're not comfortable with that.
- **Never commit credentials to Git or share them.** If a key or password is ever exposed, revoke it immediately in your OpenAI or Google account and create a new one.
- If you publish this project, add `settings.json` to your `.gitignore`.

## Cost

The app makes one OpenAI request per unread email, with at most 25 per scan. With `gpt-4o-mini` this is typically very cheap, but check your usage on the OpenAI dashboard.

## Troubleshooting

| Problem | Fix |
|---|---|
| `LOGIN failed` / authentication error | Use an app password, not your normal password. Make sure 2-Step Verification is on. |
| "OpenAI rejected the API key" | Re-enter the key and check it hasn't been revoked. |
| "Invalid scan times" | Enter 2 or 3 distinct times as `HH:MM`, separated by commas. |
| "No unread emails" | The scanner only checks unread messages. Emails you've already opened are skipped. |
| Nothing happens at scan time | The app must be running. Closing the window stops the schedule. |

## Limitations

- The app only scans while it is open; it is not a background service.
- Only unread emails are checked, and only the 25 most recent per scan.
- Results are shown in the window; there are no email or desktop notifications.

## Project structure

```
GUI.py          # the entire app
settings.json   # created on first run (server, email, scan times only)
README.md
```
