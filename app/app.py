from fastapi import FastAPI, Request
import json, os, smtplib, ssl
from email.mime.text import MIMEText
import requests
from datetime import datetime
import threading
import time
import boto3
import gzip

app = FastAPI()

# Config
LOCAL_FILE = os.getenv("LOCAL_FILE", "/data/sns_events.log")
DIGEST_INTERVAL = int(os.getenv("DIGEST_INTERVAL", "600"))   # seconds
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_TLS_MODE = os.getenv("SMTP_TLS_MODE", "SSL")  # SSL or STARTTLS
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")
S3_BUCKET = os.getenv("S3_BUCKET", "ses-events-archive")

s3 = boto3.client("s3")
lock = threading.Lock()

def send_email(subject, body):
    if not (EMAIL_USER and EMAIL_PASS and EMAIL_TO):
        print("Email env not set; skipping email send.")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    context = ssl.create_default_context()
    try:
        if SMTP_TLS_MODE.upper() == "SSL":
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
                server.login(EMAIL_USER, EMAIL_PASS)
                server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        else:  # STARTTLS
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(EMAIL_USER, EMAIL_PASS)
                server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
    except Exception as e:
        print(f"Email send failed: {e}")

def build_digest():
    """Read events from file and build summary"""
    if not os.path.exists(LOCAL_FILE):
        return None, []

    with lock:
        with open(LOCAL_FILE, "r") as f:
            lines = f.readlines()
        # clear file after reading
        open(LOCAL_FILE, "w").close()

    if not lines:
        return None, []

    events = [json.loads(line) for line in lines]
    summary = {"Delivery": 0, "Bounce": 0, "Complaint": 0, "Other": 0}

    for ev in events:
        try:
            msg = json.loads(ev["Message"])
            etype = msg.get("eventType", "Other")
        except Exception:
            etype = "Other"
        summary[etype] = summary.get(etype, 0) + 1

    body = f"SNS Digest Report ({datetime.utcnow().isoformat()} UTC)\n\n"
    for k, v in summary.items():
        body += f"- {k}: {v}\n"

    return body, events

def upload_to_s3(events):
    """Upload raw events to S3 as gzip file"""
    if not events or not S3_BUCKET:
        return

    now = datetime.utcnow()
    key = f"year={now.year}/month={now.month:02d}/day={now.day:02d}/{now.isoformat()}.json.gz"

    data = "\n".join(json.dumps(e) for e in events).encode("utf-8")
    compressed = gzip.compress(data)

    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=compressed)
    print(f"Uploaded {len(events)} events to s3://{S3_BUCKET}/{key}")

def digest_scheduler():
    """Background thread to send summary emails and upload raw events to S3"""
    while True:
        time.sleep(DIGEST_INTERVAL)
        body, events = build_digest()
        if body:
            try:
                send_email("SNS Events Digest", body)
            except Exception as e:
                print(f"Email send failed: {e}")
            try:
                upload_to_s3(events)
            except Exception as e:
                print(f"S3 upload failed: {e}")

# Start background digest thread
threading.Thread(target=digest_scheduler, daemon=True).start()

@app.post("/sns")
async def sns_listener(request: Request):
    payload = await request.json()
    msg_type = request.headers.get("x-amz-sns-message-type")

    if msg_type == "SubscriptionConfirmation":
        # Confirm the subscription
        subscribe_url = payload["SubscribeURL"]
        requests.get(subscribe_url, timeout=10)
        return {"status": "subscribed"}

    elif msg_type == "Notification":
        with lock:
            os.makedirs(os.path.dirname(LOCAL_FILE), exist_ok=True)
            with open(LOCAL_FILE, "a") as f:
                f.write(json.dumps(payload) + "\n")
        return {"status": "event buffered"}

    else:
        return {"status": "ignored"}

@app.get("/health")
def health():
    return {"ok": True}
