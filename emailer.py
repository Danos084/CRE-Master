"""
Send the weekly/daily report via Gmail SMTP.
Uses an App Password (not your Gmail login password).
Set GMAIL_APP_PASSWORD in environment or .env file.
"""

import os
import json
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

SENDER    = "propsolagent@gmail.com"
RECIPIENT = "daniel.fahey@precisionprop.com.au"

DATA_DIR  = Path("data")
EXCEL_OUT = DATA_DIR / "Bayside_Commercial_Listings.xlsx"
PPTX_OUT  = DATA_DIR / "Bayside_Commercial_Report.pptx"
LISTINGS_FILE = DATA_DIR / "listings.json"


def _load_stats() -> dict:
    if not LISTINGS_FILE.exists():
        return {"total": 0, "new": 0}
    with open(LISTINGS_FILE) as f:
        data = json.load(f)
    cutoff = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    new = sum(1 for r in data.values() if r.get("first_seen", "") >= cutoff)
    return {"total": len(data), "new": new}


def _html_body(stats: dict, report_type: str) -> str:
    today = datetime.today().strftime("%A, %d %B %Y")
    return f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:640px;margin:auto">
  <div style="background:#0D2137;padding:24px 32px;border-radius:6px 6px 0 0">
    <p style="color:#C9A84C;font-size:12px;margin:0;letter-spacing:2px">PRECISION PROPERTY</p>
    <h1 style="color:#fff;margin:8px 0 0;font-size:22px">Bayside Commercial {report_type}</h1>
    <p style="color:#aabbcc;margin:4px 0 0;font-size:13px">{today}</p>
  </div>
  <div style="background:#F4F6FA;padding:24px 32px;border-radius:0 0 6px 6px">
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      <tr>
        <td style="padding:12px;background:#fff;border-radius:4px;text-align:center;width:50%">
          <div style="font-size:32px;font-weight:bold;color:#0D2137">{stats['total']}</div>
          <div style="font-size:11px;color:#666;letter-spacing:1px">TOTAL LISTINGS</div>
        </td>
        <td style="width:12px"></td>
        <td style="padding:12px;background:#fff;border-radius:4px;text-align:center;width:50%">
          <div style="font-size:32px;font-weight:bold;color:#C9A84C">{stats['new']}</div>
          <div style="font-size:11px;color:#666;letter-spacing:1px">NEW THIS WEEK</div>
        </td>
      </tr>
    </table>
    <p style="font-size:13px;color:#444;line-height:1.6">
      Attached are your <strong>Bayside & Logan Corridor</strong> commercial lease reports,
      covering suburbs from Morningside to Wellington Point, Cleveland, Redland Bay,
      through Loganholme to Browns Plains and back via Woodridge and Slacks Creek.
    </p>
    <p style="font-size:13px;color:#444;line-height:1.6">
      <strong>Attachments:</strong><br>
      📊 &nbsp;Excel workbook — all listings + new-this-week tab<br>
      📑 &nbsp;PowerPoint report — suburb-by-suburb breakdown
    </p>
    <p style="font-size:13px;color:#444;line-height:1.6">
      Sources: <em>realcommercial.com.au</em> and <em>commercialrealestate.com.au</em>
    </p>
  </div>
  <p style="text-align:center;font-size:11px;color:#aaa;margin-top:16px">
    Precision Property &nbsp;|&nbsp; precisionprop.com.au &nbsp;|&nbsp; 0432 203 354
  </p>
</body></html>
"""


def send_report(report_type: str = "Weekly Report"):
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not password:
        # Try loading from .env in current directory
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("GMAIL_APP_PASSWORD="):
                    password = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not password:
        raise ValueError(
            "GMAIL_APP_PASSWORD not set. "
            "Create a Gmail App Password and set it as an environment variable."
        )

    stats = _load_stats()
    today = datetime.today().strftime("%d %b %Y")
    subject = f"[Precision Property] Bayside Commercial {report_type} – {today}"

    msg = MIMEMultipart("mixed")
    msg["From"]    = SENDER
    msg["To"]      = RECIPIENT
    msg["Subject"] = subject

    # HTML body
    msg.attach(MIMEText(_html_body(stats, report_type), "html"))

    # Attach Excel
    if EXCEL_OUT.exists():
        with open(EXCEL_OUT, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={EXCEL_OUT.name}")
        msg.attach(part)
    else:
        print(f"WARNING: Excel file not found at {EXCEL_OUT}")

    # Attach PPTX
    if PPTX_OUT.exists():
        with open(PPTX_OUT, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={PPTX_OUT.name}")
        msg.attach(part)
    else:
        print(f"WARNING: PPTX file not found at {PPTX_OUT}")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER, password)
        server.sendmail(SENDER, RECIPIENT, msg.as_string())

    print(f"✓ Email sent to {RECIPIENT} | {stats['total']} listings, {stats['new']} new")


if __name__ == "__main__":
    send_report("Weekly Report")
