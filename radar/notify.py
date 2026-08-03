"""Notify when the daily brief is ready.

Windows toast via PowerShell needs no extra dependency. Telegram is optional but
worth setting up — it puts the brief on your phone, which is where you will
actually read it.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

TOAST_PS1 = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] > $null
$template = @"
<toast activationType="protocol" launch="LAUNCH_URI">
  <visual><binding template="ToastGeneric">
    <text>TITLE</text>
    <text>BODY</text>
  </binding></visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Finance Radar").Show($toast)
"""


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def windows_toast(title: str, body: str, launch_path: str | Path = "") -> bool:
    """Show a Windows notification. Returns True on success."""
    try:
        uri = ""
        if launch_path:
            uri = Path(launch_path).resolve().as_uri()
        script = (TOAST_PS1
                  .replace("TITLE", _xml_escape(title[:120]))
                  .replace("BODY", _xml_escape(body[:300]))
                  .replace("LAUNCH_URI", _xml_escape(uri)))
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False,
                                         encoding="utf8") as f:
            f.write(script)
            path = f.name
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, text=True, timeout=60)
        os.unlink(path)
        return proc.returncode == 0
    except Exception:
        return False


def telegram(token: str, chat_id: str, text: str,
             image_path: str | Path | None = None) -> bool:
    """Send the brief to Telegram. Returns True on success."""
    if not token or not chat_id:
        return False
    try:
        import requests
    except ImportError:
        return False
    try:
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as fh:
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": text[:1024],
                          "parse_mode": "HTML"},
                    files={"photo": fh}, timeout=60)
        else:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": text[:4096],
                      "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=60)
        return r.ok
    except Exception:
        return False


def _email_html(day: str, analysis: dict) -> str:
    """Build the email body.

    Written for email clients, not browsers: inline styles only, tables for
    layout, no flexbox or grid. The brief's own stylesheet would be stripped by
    Gmail. The point is that the whole thing is readable on a phone without
    opening an attachment, because a file:// link to your laptop is useless
    from anywhere except your laptop.
    """
    sp = analysis.get("social_post", {}) or {}
    hook = sp.get("hook") or "Your daily brief is ready."
    stories = analysis.get("top_stories", []) or []
    teach = analysis.get("teaching_note") or {}

    rows = ""
    for s in stories[:6]:
        rows += f"""
        <tr><td style="padding:0 0 14px 0;vertical-align:top;width:26px">
          <span style="display:inline-block;width:21px;height:21px;line-height:21px;
            background:#0f766e;color:#fff;border-radius:50%;text-align:center;
            font-size:11px;font-weight:700">{s.get('rank','')}</span></td>
        <td style="padding:0 0 14px 0">
          <div style="font-size:15px;line-height:1.5;color:#12161f">
            {_xml_escape(s.get('plain_english') or s.get('headline',''))}</div>
          <div style="font-size:11px;color:#8b94a6;margin-top:3px;
            text-transform:uppercase;letter-spacing:.06em">
            {_xml_escape(s.get('category',''))}</div>
        </td></tr>"""

    lesson = ""
    if teach.get("concept"):
        lesson = f"""
      <tr><td style="padding:22px 0 0 0">
        <div style="background:#f0fdfa;border:1px solid #0f766e;border-radius:10px;padding:16px 18px">
          <div style="font-size:10px;font-weight:700;letter-spacing:.12em;
            text-transform:uppercase;color:#0f766e">Today's lesson</div>
          <div style="font-size:17px;font-weight:700;margin:5px 0 7px;color:#12161f">
            {_xml_escape(teach.get('concept',''))}</div>
          <div style="font-size:14px;line-height:1.6;color:#5b6577">
            {_xml_escape((teach.get('explanation') or '')[:420])}…</div>
        </div></td></tr>"""

    return f"""<!doctype html><html><body style="margin:0;padding:0;background:#f4f4f2">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f2">
<tr><td align="center" style="padding:24px 12px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
    style="max-width:600px;background:#fff;border-radius:14px;padding:26px 24px;
    font-family:-apple-system,'Segoe UI',Roboto,sans-serif">

    <tr><td style="font-size:11px;font-weight:700;letter-spacing:.14em;
      text-transform:uppercase;color:#0f766e">Finance Radar</td></tr>
    <tr><td style="font-size:13px;color:#8b94a6;padding:2px 0 16px">{_xml_escape(day)}</td></tr>
    <tr><td style="font-size:21px;font-weight:700;line-height:1.35;color:#12161f;
      padding-bottom:20px">{_xml_escape(hook)}</td></tr>

    <tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {rows}</table></td></tr>

    {lesson}

    <tr><td style="padding:22px 0 0 0;font-size:14px;line-height:1.6;color:#5b6577;
      border-top:1px solid #e6e8ec;margin-top:20px">
      <b style="color:#12161f">Takeaway:</b> {_xml_escape(sp.get('takeaway',''))}</td></tr>

    <tr><td style="padding:20px 0 0 0;font-size:12.5px;color:#8b94a6;line-height:1.6">
      The full brief — all ten stories, the connections between them, the jargon
      decoder and the market tables — is attached as an HTML file. Open it in any
      browser.<br><br>
      Not investment advice. Check every figure against the original source
      before acting on it.</td></tr>
  </table>
</td></tr></table></body></html>"""


def email_brief(cfg: dict, day: str, analysis: dict,
                brief_path: Path, card_path: Path | None) -> bool:
    """Email the brief. Gmail needs an App Password, not your normal password."""
    import smtplib
    from email.message import EmailMessage

    host = cfg.get("smtp_host", "smtp.gmail.com")
    port = int(cfg.get("smtp_port", 587))
    user = cfg.get("username") or os.environ.get("FINRADAR_SMTP_USER", "")
    pw = cfg.get("app_password") or os.environ.get("FINRADAR_SMTP_PASS", "")
    to = cfg.get("to") or os.environ.get("FINRADAR_MAIL_TO") or user
    if not (user and pw and to):
        return False

    sp = analysis.get("social_post", {}) or {}
    hook = sp.get("hook") or "Your daily brief is ready."

    msg = EmailMessage()
    msg["Subject"] = f"Finance Radar — {day}: {hook[:90]}"
    msg["From"] = user
    msg["To"] = to if isinstance(to, str) else ", ".join(to)
    msg.set_content(
        f"Finance Radar — {day}\n\n{hook}\n\n"
        + "\n".join(f"{s.get('rank')}. {s.get('plain_english') or s.get('headline','')}"
                    for s in (analysis.get("top_stories") or [])[:6])
        + f"\n\nTakeaway: {sp.get('takeaway','')}\n\n"
          "The full brief is attached as an HTML file.")
    msg.add_alternative(_email_html(day, analysis), subtype="html")

    for path, mime in ((brief_path, ("text", "html")), (card_path, ("image", "png"))):
        if path and Path(path).exists():
            msg.add_attachment(Path(path).read_bytes(), maintype=mime[0],
                               subtype=mime[1], filename=Path(path).name)

    try:
        with smtplib.SMTP(host, port, timeout=60) as srv:
            srv.starttls()
            srv.login(user, pw)
            srv.send_message(msg)
        return True
    except Exception:
        return False


def announce(cfg: dict, day: str, analysis: dict,
             brief_path: Path, card_path: Path | None) -> dict:
    """Fire every configured notification channel. Never raises."""
    sp = analysis.get("social_post", {}) or {}
    hook = sp.get("hook") or "Your daily brief is ready."
    n_stories = len(analysis.get("top_stories", []))
    results = {}

    if cfg.get("windows_toast", True):
        results["toast"] = windows_toast(
            f"Finance Radar — {day}",
            f"{hook}\n{n_stories} stories analysed. Click to open the brief.",
            brief_path)

    tg = cfg.get("telegram") or {}
    token = tg.get("bot_token") or os.environ.get("FINRADAR_TG_TOKEN", "")
    chat = tg.get("chat_id") or os.environ.get("FINRADAR_TG_CHAT", "")
    if token and chat:
        scenario = (analysis.get("scenario") or "")[:900]
        body = (f"<b>Finance Radar — {day}</b>\n\n"
                f"<b>{hook}</b>\n\n{sp.get('body', '')}\n\n"
                f"<i>{sp.get('takeaway', '')}</i>\n\n"
                f"— — —\n{scenario}")
        results["telegram"] = telegram(token, chat, body, card_path)

    # Email turns itself on when the credentials are in the environment, which
    # is how the cloud runner supplies them — no config edit needed there.
    mail = dict(cfg.get("email") or {})
    from_env = bool(os.environ.get("FINRADAR_SMTP_USER")
                    and os.environ.get("FINRADAR_SMTP_PASS"))
    if mail.get("enabled") or from_env:
        mail.setdefault("to", os.environ.get("FINRADAR_MAIL_TO", ""))
        results["email"] = email_brief(mail, day, analysis, brief_path, card_path)

    return results
