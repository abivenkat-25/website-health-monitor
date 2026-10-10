from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import csv
import io
import time

app = Flask(__name__)
app.secret_key = "change-this-local-demo-key"

BASE_DIR = Path(__file__).resolve().parent
REPORT_FILE = BASE_DIR / "monitor_report.csv"

FIELDS = [
    "URL",
    "Status",
    "HTTP Code",
    "Response Time (ms)",
    "Performance",
    "Checked At",
]


def read_records():
    """Read all saved checks from the CSV report."""
    if not REPORT_FILE.exists() or REPORT_FILE.stat().st_size == 0:
        return []

    try:
        with REPORT_FILE.open("r", newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))
    except (OSError, csv.Error):
        return []


def save_record(record):
    """Append one check to the CSV report."""
    needs_header = not REPORT_FILE.exists() or REPORT_FILE.stat().st_size == 0

    with REPORT_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerow(record)


def performance_rating(response_time):
    if response_time < 500:
        return "Fast"
    elif response_time < 1500:
        return "Moderate"
    return "Slow"


def check_website(raw_url):
    url = raw_url.strip()

    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    status = "UNAVAILABLE"
    status_code = "N/A"
    started = time.perf_counter()

    try:
        request_obj = Request(
            url,
            headers={"User-Agent": "WebsiteHealthMonitor/1.0"}
        )
        with urlopen(request_obj, timeout=5) as response:
            status_code = response.status
            status = "ONLINE"

    except HTTPError as error:
        # An HTTP response such as 404 or 503 means the server responded.
        status_code = error.code
        status = "HTTP ERROR"
        error.close()

    except (URLError, TimeoutError, OSError, ValueError) as error:
        # Keep the detail in the server terminal for debugging.
        print(f"Could not check {url}: {error}")

    response_time = round((time.perf_counter() - started) * 1000, 2)
    rating = "N/A" if status_code == "N/A" else performance_rating(response_time)

    return {
        "URL": url,
        "Status": status,
        "HTTP Code": status_code,
        "Response Time (ms)": response_time,
        "Performance": rating,
        "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_summary(records):
    total = len(records)
    online = sum(1 for item in records if item.get("Status") == "ONLINE")
    http_errors = sum(1 for item in records if item.get("Status") == "HTTP ERROR")
    unavailable = sum(1 for item in records if item.get("Status") == "UNAVAILABLE")

    return {
        "total": total,
        "online": online,
        "http_errors": http_errors,
        "unavailable": unavailable,
    }


@app.route("/", methods=["GET"])
def index():
    records = read_records()
    # Show newest checks first.
    recent_records = list(reversed(records[-50:]))
    return render_template(
        "index.html",
        records=recent_records,
        summary=get_summary(records),
    )


@app.route("/check", methods=["POST"])
def check():
    raw_urls = request.form.get("urls", "")
    # Accept one URL per line, or several URLs separated by commas.
    urls = [
        part.strip()
        for line in raw_urls.splitlines()
        for part in line.split(",")
        if part.strip()
    ]

    if not urls:
        flash("Please enter at least one website URL.", "error")
        return redirect(url_for("index"))

    if len(urls) > 20:
        flash("Please check up to 20 URLs at a time.", "error")
        return redirect(url_for("index"))

    for url in urls:
        record = check_website(url)
        if record:
            save_record(record)

    flash(f"Finished checking {len(urls)} website(s).", "success")
    return redirect(url_for("index"))


@app.route("/download", methods=["GET"])
def download_report():
    records = read_records()
    if not records:
        flash("There is no report to download yet. Check a website first.", "error")
        return redirect(url_for("index"))

    # Send the saved CSV as a browser download.
    return send_file(
        REPORT_FILE,
        mimetype="text/csv",
        as_attachment=True,
        download_name="website_health_report.csv",
    )


@app.route("/clear", methods=["POST"])
def clear_report():
    # Clear history only after the user confirms in the browser prompt.
    if REPORT_FILE.exists():
        REPORT_FILE.unlink()
    flash("Report history cleared.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Local development server. Keep debug off for safer default behavior.
    app.run(host="127.0.0.1", port=5000, debug=False)
