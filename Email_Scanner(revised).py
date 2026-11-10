"""
Dylan D, November 10th, 2026

Email Scanner Agent - a simple tkinter GUI.

Scans your inbox 2-3 times a day, sends unread emails to OpenAI to check
for job interviews or acceptance letters, and shows a countdown to the next scan.

Credentials are never hardcoded. Supply them any of these ways (highest priority first):
  1. Command-line arguments:
       python GUI.py --email you@gmail.com --password "abcd efgh ijkl mnop" --api-key sk-...
  2. Environment variables: EMAIL_USER, EMAIL_APP_PASSWORD, OPENAI_API_KEY
  3. Typing them into the app's Settings fields

Only non-secret settings (server, email, scan times) are remembered between runs,
in settings.json next to this script. The app password and API key are never saved.
"""

import argparse
import email
import imaplib
import json
import os
import queue
import re
import threading
import tkinter as tk
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from tkinter import messagebox, scrolledtext, ttk

from openai import OpenAI


MODEL = "gpt-4o-mini"
DEFAULT_HOST = "imap.gmail.com"
DEFAULT_TIMES = "08:00, 13:00, 19:00"   # 2-3 scan times per day (24h, HH:MM)
MAX_EMAILS = 25                          # most recent unread emails per scan
BODY_CHARS = 1500                        # body characters sent per email
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")



def load_settings():
    """Load saved non-secret settings."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(host, user, times):
    """Save only non-secret settings. Passwords and API keys are never written."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"host": host, "user": user, "times": times}, f, indent=2)
    except OSError:
        pass


def parse_args():
    parser = argparse.ArgumentParser(description="Job Email Scanner Agent")
    parser.add_argument("--email", help="Email address to scan")
    parser.add_argument("--password", help="Email app password")
    parser.add_argument("--api-key", dest="api_key", help="OpenAI API key")
    parser.add_argument("--host", help=f"IMAP server (default {DEFAULT_HOST})")
    parser.add_argument("--times", help='Scan times, e.g. "08:00, 13:00, 19:00"')
    return parser.parse_args()



def decode(value):
    """Decode a possibly MIME-encoded header into plain text."""
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def get_body(msg):
    """Extract readable text from an email message, truncated."""
    text, html = "", ""
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        try:
            decoded = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except LookupError:
            decoded = payload.decode("utf-8", errors="replace")
        if ctype == "text/plain":
            text += decoded
        else:
            html += decoded
    if not text and html:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()[:BODY_CHARS]


def fetch_unread(host, user, password):
    """Return (emails, total_unread). Opens the mailbox read-only."""
    imap = imaplib.IMAP4_SSL(host)
    try:
        imap.login(user, password)
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, "UNSEEN")
        all_ids = data[0].split()
        emails = []
        for msg_id in all_ids[-MAX_EMAILS:]:
            _, msg_data = imap.fetch(msg_id, "(BODY.PEEK[])")
            msg = email.message_from_bytes(msg_data[0][1])
            emails.append({
                "from": decode(msg.get("From")),
                "subject": decode(msg.get("Subject")),
                "date": msg.get("Date", ""),
                "body": get_body(msg),
            })
        return emails, len(all_ids)
    finally:
        try:
            imap.logout()
        except Exception:
            pass



def analyze(emails, api_key):
    """Send each email through OpenAI, returning ONLY job interviews/acceptances.

    The client is built from the key the user supplied, so no key lives in the code.
    """
    client = OpenAI(api_key=api_key)
    matched_results = []
    errors = 0

    for e in emails:
        prompt = f"""
        Analyze the following email to see if it is a job interview invitation, a job offer, or a job acceptance letter.
        Subject: {e['subject']}
        Body: {e['body']}

        Return a JSON object with this exact format:
        {{"is_match": true/false, "category": "interview" | "acceptance" | "none", "company": "Company Name or unknown", "summary": "Brief summary of the email"}}
        """
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)

            if data.get("is_match") is True:
                matched_results.append(
                    f"🎯 MATCH FOUND!\n"
                    f"Company: {data.get('company', 'Unknown')}\n"
                    f"Category: {data.get('category', '').upper()}\n"
                    f"From: {e['from']}\n"
                    f"Subject: {e['subject']}\n"
                    f"Summary: {data.get('summary', '')}\n"
                    f"{'-' * 40}"
                )
        except Exception as err:
            errors += 1
            # An invalid key fails every email; surface it instead of hiding it.
            if "api key" in str(err).lower() or "401" in str(err):
                raise RuntimeError("OpenAI rejected the API key. Check it and try again.") from err
            continue

    if matched_results:
        return "\n\n".join(matched_results)
    note = f" ({errors} email(s) could not be analyzed)" if errors else ""
    return f"No job interviews or acceptance letters found in this batch. All clear!{note}"



def parse_times(text):
    """Parse 'HH:MM, HH:MM' into a sorted list of (hour, minute). Requires 2-3 times."""
    times = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if chunk:
            t = datetime.strptime(chunk, "%H:%M")
            times.append((t.hour, t.minute))
    times = sorted(set(times))
    if not 2 <= len(times) <= 3:
        raise ValueError("Enter 2 or 3 distinct times, e.g. 08:00, 13:00, 19:00")
    return times


def next_scan_after(times, now):
    """Return the next scheduled datetime strictly after `now`."""
    candidates = []
    for day in (0, 1):
        base = now + timedelta(days=day)
        for hour, minute in times:
            t = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if t > now:
                candidates.append(t)
    return min(candidates)



class EmailAgentApp:
    def __init__(self, root, args):
        self.root = root
        root.title("Job Email Scanner Agent")
        root.geometry("720x680")
        root.minsize(600, 560)

        self.q = queue.Queue()
        self.scanning = False
        self.schedule_on = False
        self.times = []
        self.next_scan = None

        saved = load_settings()

        # User-supplied values live in these variables. Priority: CLI > env > saved > default.
        self.host = tk.StringVar(value=args.host or saved.get("host") or DEFAULT_HOST)
        self.user = tk.StringVar(
            value=args.email or os.environ.get("EMAIL_USER") or saved.get("user", "")
        )
        self.password = tk.StringVar(
            value=args.password or os.environ.get("EMAIL_APP_PASSWORD", "")
        )
        self.api_key = tk.StringVar(
            value=args.api_key or os.environ.get("OPENAI_API_KEY", "")
        )
        self.times_text = tk.StringVar(
            value=args.times or saved.get("times") or DEFAULT_TIMES
        )

        self._build_ui()
        self._tick()
        self._poll_queue()

        # Auto-start only when everything was supplied up front (e.g. via CLI/env).
        if self.host.get() and self.user.get() and self.password.get() and self.api_key.get():
            self.toggle_schedule()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}

        # Settings
        settings = ttk.LabelFrame(self.root, text="Settings")
        settings.pack(fill="x", padx=10, pady=(10, 4))
        settings.columnconfigure(1, weight=1)
        rows = [
            ("IMAP server", self.host, None),
            ("Email address", self.user, None),
            ("App password", self.password, "*"),
            ("OpenAI API key", self.api_key, "*"),
            ("Scan times (24h)", self.times_text, None),
        ]
        for i, (label, var, show) in enumerate(rows):
            ttk.Label(settings, text=label).grid(row=i, column=0, sticky="w", **pad)
            ttk.Entry(settings, textvariable=var, show=show or "").grid(
                row=i, column=1, sticky="ew", **pad
            )
        ttk.Label(
            settings,
            text="Your password and API key are kept in memory only and never saved to disk.",
            foreground="gray",
        ).grid(row=len(rows), column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

        # Countdown
        timer = ttk.LabelFrame(self.root, text="Next scan")
        timer.pack(fill="x", padx=10, pady=4)
        self.countdown = ttk.Label(timer, text="--:--:--", font=("Helvetica", 32, "bold"))
        self.countdown.pack(pady=(8, 0))
        self.next_label = ttk.Label(timer, text="Schedule is stopped")
        self.next_label.pack(pady=(0, 8))

        # Buttons
        buttons = ttk.Frame(self.root)
        buttons.pack(fill="x", padx=10, pady=4)
        self.toggle_btn = ttk.Button(buttons, text="Start schedule", command=self.toggle_schedule)
        self.toggle_btn.pack(side="left", padx=(0, 6))
        self.scan_btn = ttk.Button(buttons, text="Scan now", command=self.scan_now)
        self.scan_btn.pack(side="left")
        self.status = ttk.Label(buttons, text="Idle")
        self.status.pack(side="right")

        # Results
        results = ttk.LabelFrame(self.root, text="Latest report")
        results.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.output = scrolledtext.ScrolledText(results, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True, padx=6, pady=6)

    # ---- schedule control ----
    def toggle_schedule(self):
        if self.schedule_on:
            self.schedule_on = False
            self.next_scan = None
            self.toggle_btn.config(text="Start schedule")
            self.next_label.config(text="Schedule is stopped")
            self.countdown.config(text="--:--:--")
            return
        try:
            self.times = parse_times(self.times_text.get())
        except ValueError as exc:
            messagebox.showerror("Invalid scan times", str(exc))
            return
        if not self._credentials_ok():
            return
        save_settings(self.host.get().strip(), self.user.get().strip(), self.times_text.get().strip())
        self.schedule_on = True
        self.next_scan = next_scan_after(self.times, datetime.now())
        self.toggle_btn.config(text="Stop schedule")

    def _credentials_ok(self):
        if not (self.host.get().strip() and self.user.get().strip()
                and self.password.get().strip() and self.api_key.get().strip()):
            messagebox.showwarning(
                "Missing info",
                "Enter the IMAP server, email address, app password, and OpenAI API key.",
            )
            return False
        return True

    # ---- timer loop (runs every second) ----
    def _tick(self):
        if self.schedule_on and self.next_scan:
            now = datetime.now()
            if now >= self.next_scan:
                self.start_scan()
                self.next_scan = next_scan_after(self.times, now)
            remaining = max(0, int((self.next_scan - now).total_seconds()))
            h, rem = divmod(remaining, 3600)
            m, s = divmod(rem, 60)
            self.countdown.config(text=f"{h:02d}:{m:02d}:{s:02d}")
            self.next_label.config(text=f"Next scan at {self.next_scan:%a %H:%M}")
        self.root.after(1000, self._tick)

    # ---- scanning ----
    def scan_now(self):
        if self._credentials_ok():
            self.start_scan()

    def start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_btn.config(state="disabled")
        self.status.config(text="Scanning...")

        # Read the user's current inputs on the main thread, then hand them to the worker.
        host = self.host.get().strip()
        user = self.user.get().strip()
        pw = self.password.get().strip()
        key = self.api_key.get().strip()

        def work():
            try:
                emails, total = fetch_unread(host, user, pw)
                report = analyze(emails, key) if emails else "No unread emails."
                self.q.put(("done", report, total, len(emails)))
            except Exception as exc:
                self.q.put(("error", f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                kind, *payload = self.q.get_nowait()
                stamp = datetime.now().strftime("%a %b %d, %H:%M")
                if kind == "done":
                    report, total, analyzed = payload
                    header = f"Scan at {stamp} - {total} unread, {analyzed} analyzed\n{'-' * 50}\n"
                    self._show(header + report)
                    self.status.config(text=f"Last scan {stamp}")
                else:
                    self._show(f"Scan at {stamp} failed:\n{payload[0]}")
                    self.status.config(text="Last scan failed")
                self.scanning = False
                self.scan_btn.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    def _show(self, text):
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.config(state="disabled")


if __name__ == "__main__":
    args = parse_args()
    root = tk.Tk()
    EmailAgentApp(root, args)
    root.mainloop()
