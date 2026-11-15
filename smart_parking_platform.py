import os
import tkinter as tk
from tkinter import messagebox, ttk
import sqlite3
import smtplib
import ssl
import random
import re
import webbrowser
from urllib.parse import urlparse
from email.mime.text import MIMEText
from datetime import datetime, timedelta


# ============================================================
#                    EMAIL SETTINGS
# ============================================================

# Credentials are read from environment variables so they are never
# committed to GitHub. See README.md for how to set them.
ADMIN_EMAIL = os.environ.get("PARKING_ADMIN_EMAIL", "")
ADMIN_APP_PASSWORD = os.environ.get("PARKING_APP_PASSWORD", "")


# ============================================================
#                    DATABASE
# ============================================================

DB_NAME = "parking.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()


# ============================================================
#                    DATABASE MIGRATION
# ============================================================

def get_table_columns(table_name):

    cursor.execute(
        f"PRAGMA table_info({table_name})"
    )

    return [
        row[1]
        for row in cursor.fetchall()
    ]


def add_column_if_missing(
    table_name,
    column_name,
    column_definition
):

    columns = get_table_columns(table_name)

    if column_name not in columns:

        cursor.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name}
            {column_definition}
            """
        )

        conn.commit()


# ============================================================
#                    OWNERS TABLE
# ============================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS owners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")


# ============================================================
#                    REQUESTS TABLE
# ============================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_email TEXT NOT NULL,
    mall TEXT NOT NULL,
    location TEXT NOT NULL,
    slots INTEGER NOT NULL,
    price REAL NOT NULL,
    status TEXT DEFAULT 'pending'
)
""")


# ============================================================
#                    BOOKINGS TABLE
# ============================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    vehicle TEXT NOT NULL,
    mall TEXT NOT NULL,
    slot INTEGER NOT NULL,
    start_datetime TEXT NOT NULL,
    end_datetime TEXT NOT NULL,
    price_per_minute REAL NOT NULL,
    total_cost REAL NOT NULL,
    status TEXT DEFAULT 'active'
)
""")

conn.commit()


# ============================================================
#                    DATABASE FIX
# ============================================================

booking_columns = get_table_columns("bookings")

if "slot" not in booking_columns:

    cursor.execute("""
        ALTER TABLE bookings
        ADD COLUMN slot INTEGER
    """)

    conn.commit()

    booking_columns = get_table_columns("bookings")

    if "slot_number" in booking_columns:

        cursor.execute("""
            UPDATE bookings
            SET slot = slot_number
            WHERE slot IS NULL
        """)

        conn.commit()

    elif "parking_slot" in booking_columns:

        cursor.execute("""
            UPDATE bookings
            SET slot = parking_slot
            WHERE slot IS NULL
        """)

        conn.commit()


# ============================================================
#                    ENSURE REQUEST COLUMNS
# ============================================================

add_column_if_missing(
    "requests",
    "owner_email",
    "TEXT"
)

add_column_if_missing(
    "requests",
    "mall",
    "TEXT"
)

add_column_if_missing(
    "requests",
    "location",
    "TEXT"
)

add_column_if_missing(
    "requests",
    "slots",
    "INTEGER"
)

add_column_if_missing(
    "requests",
    "price",
    "REAL"
)

add_column_if_missing(
    "requests",
    "status",
    "TEXT DEFAULT 'pending'"
)


# ============================================================
#                    ENSURE BOOKING COLUMNS
# ============================================================

add_column_if_missing(
    "bookings",
    "customer_name",
    "TEXT"
)

add_column_if_missing(
    "bookings",
    "customer_email",
    "TEXT"
)

add_column_if_missing(
    "bookings",
    "vehicle",
    "TEXT"
)

add_column_if_missing(
    "bookings",
    "mall",
    "TEXT"
)

add_column_if_missing(
    "bookings",
    "slot",
    "INTEGER"
)

add_column_if_missing(
    "bookings",
    "start_datetime",
    "TEXT"
)

add_column_if_missing(
    "bookings",
    "end_datetime",
    "TEXT"
)

add_column_if_missing(
    "bookings",
    "price_per_minute",
    "REAL"
)

add_column_if_missing(
    "bookings",
    "total_cost",
    "REAL"
)

add_column_if_missing(
    "bookings",
    "status",
    "TEXT DEFAULT 'active'"
)

conn.commit()


# ============================================================
#                    GLOBAL VARIABLES
# ============================================================

generated_otp = None
otp_email = None
otp_expiry = None

logged_owner_email = None

selected_customer_slot = None

slot_buttons = {}

# IMPORTANT:
# Stores the currently scheduled refresh.
# This prevents multiple refresh callbacks.
refresh_job = None


# ============================================================
#                    GOOGLE MAPS FUNCTIONS
# ============================================================

def is_google_maps_url(location):

    if not location:
        return False

    location = location.strip()

    try:

        parsed = urlparse(location)

        if parsed.scheme.lower() != "https":
            return False

        hostname = parsed.netloc.lower()
        hostname = hostname.split(":")[0]

        accepted_hosts = {
            "google.com",
            "www.google.com",
            "maps.google.com",
            "maps.app.goo.gl",
            "goo.gl"
        }

        if hostname not in accepted_hosts:
            return False

        if hostname in {
            "google.com",
            "www.google.com",
            "maps.google.com"
        }:

            if not parsed.path.lower().startswith("/maps"):
                return False

        if hostname in {
            "maps.app.goo.gl",
            "goo.gl"
        }:

            if not parsed.path:
                return False

        return True

    except Exception:

        return False


def validate_location(location):

    location = location.strip()

    if not location:

        return (
            False,
            "Google Maps location link cannot be empty."
        )

    if len(location) < 15:

        return (
            False,
            "Please paste the complete Google Maps location link."
        )

    if not is_google_maps_url(location):

        return (
            False,
            "Invalid Google Maps link.\n\n"
            "Please paste the exact Google Maps URL.\n\n"
            "Examples:\n"
            "https://www.google.com/maps/...\n"
            "https://maps.app.goo.gl/..."
        )

    return True, ""


def get_exact_google_maps_url(location):

    location = location.strip()

    if not is_google_maps_url(location):
        return None

    return location


def open_location_in_google_maps(location=None):

    if location is None:
        location = location_entry.get().strip()

    if not location:

        messagebox.showwarning(
            "Location Required",
            "Please paste the exact Google Maps link first."
        )

        return

    valid, error_message = validate_location(location)

    if not valid:

        messagebox.showerror(
            "Invalid Google Maps Link",
            error_message
        )

        return

    maps_url = get_exact_google_maps_url(location)

    if not maps_url:

        messagebox.showerror(
            "Location Error",
            "The Google Maps URL could not be verified."
        )

        return

    try:

        webbrowser.open(maps_url)

    except Exception as e:

        messagebox.showerror(
            "Google Maps Error",
            f"Could not open Google Maps.\n\n{e}"
        )


def open_customer_location():

    mall = selected_mall.get()

    if not mall or mall == "No approved parking":

        messagebox.showwarning(
            "No Mall Selected",
            "Please select an approved parking mall first."
        )

        return

    info = get_mall_info(mall)

    if not info:

        messagebox.showerror(
            "Location Error",
            "Mall information could not be found."
        )

        return

    exact_maps_url = info[1]

    if not exact_maps_url:

        messagebox.showerror(
            "Location Error",
            "No Google Maps location is available."
        )

        return

    if not is_google_maps_url(exact_maps_url):

        messagebox.showerror(
            "Location Error",
            "The saved location is not a valid Google Maps URL."
        )

        return

    try:

        webbrowser.open(exact_maps_url)

    except Exception as e:

        messagebox.showerror(
            "Google Maps Error",
            f"Could not open Google Maps.\n\n{e}"
        )


# ============================================================
#                    EMAIL FUNCTION
# ============================================================

def send_email(to_email, subject, body):

    try:

        to_email = to_email.strip()

        if not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            to_email
        ):

            messagebox.showerror(
                "Invalid Email",
                f"Invalid email address:\n{to_email}"
            )

            return False

        if (
            not ADMIN_EMAIL.strip()
            or not ADMIN_APP_PASSWORD.strip()
        ):

            messagebox.showerror(
                "Email Setup Required",
                "Please set the PARKING_ADMIN_EMAIL and "
                "PARKING_APP_PASSWORD environment variables.\n\n"
                "See README.md for instructions."
            )

            return False

        msg = MIMEText(body)

        msg["Subject"] = subject
        msg["From"] = ADMIN_EMAIL
        msg["To"] = to_email

        context = ssl.create_default_context()

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=30,
            context=context
        ) as server:

            server.login(
                ADMIN_EMAIL,
                ADMIN_APP_PASSWORD
            )

            server.sendmail(
                ADMIN_EMAIL,
                [to_email],
                msg.as_string()
            )

        return True

    except Exception as e:

        messagebox.showerror(
            "Email Error",
            f"Could not send email:\n\n{e}"
        )

        return False


# ============================================================
#                    EMAIL VALIDATION
# ============================================================

def valid_email(email):

    return re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+",
        email.strip()
    )


# ============================================================
#                    OWNER LOGIN / REGISTER
# ============================================================

def owner_login_register():

    global logged_owner_email

    email = owner_email_entry.get().strip()
    password = owner_password_entry.get().strip()

    if not valid_email(email):

        messagebox.showerror(
            "Invalid Email",
            "Please enter a valid email address."
        )

        return

    if not password:

        messagebox.showerror(
            "Password Required",
            "Please enter a password."
        )

        return

    cursor.execute(
        """
        SELECT email, password
        FROM owners
        WHERE email = ?
        """,
        (email,)
    )

    owner = cursor.fetchone()

    if owner is None:

        try:

            cursor.execute(
                """
                INSERT INTO owners
                (email, password)
                VALUES (?, ?)
                """,
                (email, password)
            )

            conn.commit()

            messagebox.showinfo(
                "Registration Successful",
                "Owner registered successfully.\n\n"
                "Now click Send OTP."
            )

        except Exception as e:

            messagebox.showerror(
                "Registration Error",
                str(e)
            )

    else:

        if owner[1] != password:

            messagebox.showerror(
                "Login Failed",
                "Incorrect password."
            )

            return

        messagebox.showinfo(
            "Password Verified",
            "Password verified successfully.\n\n"
            "Now click Send OTP."
        )


# ============================================================
#                    SEND OWNER OTP
# ============================================================

def send_owner_otp():

    global generated_otp
    global otp_email
    global otp_expiry

    email = owner_email_entry.get().strip()

    if not valid_email(email):

        messagebox.showerror(
            "Invalid Email",
            "Please enter a valid email address."
        )

        return

    cursor.execute(
        """
        SELECT email
        FROM owners
        WHERE email = ?
        """,
        (email,)
    )

    owner = cursor.fetchone()

    if owner is None:

        messagebox.showwarning(
            "Not Registered",
            "Please click Login / Register first."
        )

        return

    generated_otp = str(
        random.randint(100000, 999999)
    )

    otp_email = email

    otp_expiry = (
        datetime.now() +
        timedelta(minutes=5)
    )

    body = f"""
SMART PARKING PLATFORM

Your Owner Login OTP is:

{generated_otp}

This OTP is valid for 5 minutes.

Do not share this OTP with anyone.
"""

    success = send_email(
        email,
        "Smart Parking Platform - Owner OTP",
        body
    )

    if success:

        messagebox.showinfo(
            "OTP Sent",
            "OTP has been sent to your email."
        )


# ============================================================
#                    VERIFY OWNER OTP
# ============================================================

def verify_owner_otp():

    global logged_owner_email

    entered_otp = owner_otp_entry.get().strip()

    if generated_otp is None:

        messagebox.showwarning(
            "OTP Required",
            "Please click Send OTP first."
        )

        return

    if (
        otp_expiry and
        datetime.now() > otp_expiry
    ):

        messagebox.showerror(
            "OTP Expired",
            "OTP has expired.\n\n"
            "Please request a new OTP."
        )

        return

    if entered_otp != generated_otp:

        messagebox.showerror(
            "Invalid OTP",
            "Incorrect OTP."
        )

        return

    logged_owner_email = otp_email

    owner_status_label.config(
        text=f"Logged in as: {logged_owner_email}",
        fg="green"
    )

    messagebox.showinfo(
        "Login Successful",
        "Owner login successful!"
    )


# ============================================================
#                    SEND PARKING REQUEST
# ============================================================

def send_parking_request():

    if logged_owner_email is None:

        messagebox.showwarning(
            "Login Required",
            "Please login and verify OTP first."
        )

        return

    mall = mall_entry.get().strip()
    location = location_entry.get().strip()
    slots_text = slots_entry.get().strip()
    price_text = price_entry.get().strip()

    if not mall:

        messagebox.showwarning(
            "Missing Mall Name",
            "Please enter the shopping mall name."
        )

        return

    if not location:

        messagebox.showwarning(
            "Missing Google Maps Link",
            "Please paste the exact Google Maps location link."
        )

        return

    location_valid, location_error = validate_location(
        location
    )

    if not location_valid:

        messagebox.showerror(
            "Invalid Google Maps Link",
            location_error
        )

        return

    if not slots_text or not price_text:

        messagebox.showwarning(
            "Missing Information",
            "Please fill Total Slots and Price."
        )

        return

    try:

        slots = int(slots_text)
        price = float(price_text)

        if slots <= 0 or price <= 0:
            raise ValueError

    except ValueError:

        messagebox.showerror(
            "Invalid Input",
            "Total Slots must be a positive integer\n"
            "and Price must be a positive number."
        )

        return

    exact_maps_url = get_exact_google_maps_url(location)

    if not exact_maps_url:

        messagebox.showerror(
            "Location Error",
            "Could not save the Google Maps URL."
        )

        return

    cursor.execute(
        """
        SELECT id
        FROM requests
        WHERE mall = ?
        AND location = ?
        AND status IN ('pending', 'approved')
        """,
        (mall, exact_maps_url)
    )

    if cursor.fetchone():

        messagebox.showwarning(
            "Already Exists",
            "This mall already has a pending "
            "or approved request with this location."
        )

        return

    cursor.execute(
        """
        INSERT INTO requests
        (
            owner_email,
            mall,
            location,
            slots,
            price,
            status
        )
        VALUES (?, ?, ?, ?, ?, 'pending')
        """,
        (
            logged_owner_email,
            mall,
            exact_maps_url,
            slots,
            price
        )
    )

    conn.commit()

    body = f"""
SMART PARKING PLATFORM

NEW PARKING REQUEST

============================

Owner Email:
{logged_owner_email}

Mall Name:
{mall}

Exact Google Maps Location:
{exact_maps_url}

Total Slots:
{slots}

Price Per Minute:
₹{price}

Status:
Pending

Please open the Admin Panel to approve
or reject this request.

============================
"""

    email_success = send_email(
        ADMIN_EMAIL,
        "New Smart Parking Approval Request",
        body
    )

    if email_success:

        messagebox.showinfo(
            "Request Submitted",
            "Parking request submitted successfully.\n\n"
            "The exact Google Maps location has been saved.\n\n"
            "Admin has been notified."
        )

    else:

        messagebox.showwarning(
            "Request Saved",
            "Parking request was saved,\n"
            "but email notification failed."
        )

    mall_entry.delete(0, tk.END)
    location_entry.delete(0, tk.END)
    slots_entry.delete(0, tk.END)
    price_entry.delete(0, tk.END)


# ============================================================
#                    ADMIN PANEL
# ============================================================

def admin_panel():

    admin_window = tk.Toplevel(root)

    admin_window.title(
        "Smart Parking - Admin Panel"
    )

    admin_window.geometry(
        "1200x700"
    )

    admin_window.grab_set()

    tk.Label(
        admin_window,
        text="ADMIN PANEL",
        font=("Arial", 22, "bold")
    ).pack(pady=15)

    request_frame_admin = tk.LabelFrame(
        admin_window,
        text="Parking Requests",
        font=("Arial", 13, "bold")
    )

    request_frame_admin.pack(
        fill="x",
        padx=20,
        pady=10
    )

    columns = (
        "ID",
        "Owner",
        "Mall",
        "Google Maps Location",
        "Slots",
        "Price",
        "Status"
    )

    tree = ttk.Treeview(
        request_frame_admin,
        columns=columns,
        show="headings",
        height=8
    )

    for col in columns:

        tree.heading(
            col,
            text=col
        )

        if col == "Google Maps Location":

            tree.column(
                col,
                width=350
            )

        elif col == "Owner":

            tree.column(
                col,
                width=180
            )

        else:

            tree.column(
                col,
                width=100
            )

    tree.pack(
        fill="x",
        padx=10,
        pady=10
    )

    def load_requests():

        for item in tree.get_children():
            tree.delete(item)

        cursor.execute(
            """
            SELECT
                id,
                owner_email,
                mall,
                location,
                slots,
                price,
                status
            FROM requests
            ORDER BY id DESC
            """
        )

        for row in cursor.fetchall():

            tree.insert(
                "",
                tk.END,
                values=row
            )

    load_requests()


    # ========================================================
    # APPROVE
    # ========================================================

    def approve_request():

        selected = tree.selection()

        if not selected:

            messagebox.showwarning(
                "Select Request",
                "Please select a request."
            )

            return

        values = tree.item(
            selected[0],
            "values"
        )

        request_id = values[0]
        owner_email = values[1]
        mall = values[2]
        exact_maps_url = values[3]

        if not is_google_maps_url(exact_maps_url):

            messagebox.showerror(
                "Invalid Location",
                "This request does not contain a valid "
                "Google Maps URL."
            )

            return

        cursor.execute(
            """
            UPDATE requests
            SET status = 'approved'
            WHERE id = ?
            """,
            (request_id,)
        )

        conn.commit()

        send_email(
            owner_email,
            "Parking Request Approved",
            f"""
Congratulations!

Your parking request has been APPROVED.

Mall:
{mall}

Exact Google Maps Location:
{exact_maps_url}

Your mall is now available
in the customer booking system.

Thank you,
Smart Parking Platform
"""
        )

        load_requests()
        load_approved_malls()

        messagebox.showinfo(
            "Approved",
            f"{mall} has been approved.\n\n"
            "The Google Maps location is now "
            "available to customers."
        )


    # ========================================================
    # REJECT
    # ========================================================

    def reject_request():

        selected = tree.selection()

        if not selected:

            messagebox.showwarning(
                "Select Request",
                "Please select a request."
            )

            return

        values = tree.item(
            selected[0],
            "values"
        )

        request_id = values[0]
        owner_email = values[1]
        mall = values[2]

        cursor.execute(
            """
            UPDATE requests
            SET status = 'rejected'
            WHERE id = ?
            """,
            (request_id,)
        )

        conn.commit()

        send_email(
            owner_email,
            "Parking Request Rejected",
            f"""
Your parking request has been rejected.

Mall:
{mall}

Please contact the administrator
for more information.

Smart Parking Platform
"""
        )

        load_requests()
        load_approved_malls()

        messagebox.showinfo(
            "Rejected",
            f"{mall} request has been rejected."
        )


    button_frame = tk.Frame(admin_window)

    button_frame.pack(pady=10)

    tk.Button(
        button_frame,
        text="APPROVE",
        command=approve_request,
        bg="green",
        fg="white",
        font=("Arial", 11, "bold"),
        width=15
    ).grid(
        row=0,
        column=0,
        padx=10
    )

    tk.Button(
        button_frame,
        text="REJECT",
        command=reject_request,
        bg="red",
        fg="white",
        font=("Arial", 11, "bold"),
        width=15
    ).grid(
        row=0,
        column=1,
        padx=10
    )


    # ========================================================
    # APPROVED PARKING
    # ========================================================

    approved_frame = tk.LabelFrame(
        admin_window,
        text="Approved Parking",
        font=("Arial", 13, "bold")
    )

    approved_frame.pack(
        fill="both",
        expand=True,
        padx=20,
        pady=10
    )

    approved_tree = ttk.Treeview(
        approved_frame,
        columns=(
            "Mall",
            "Google Maps Location",
            "Slots",
            "Price",
            "Owner"
        ),
        show="headings"
    )

    for col in (
        "Mall",
        "Google Maps Location",
        "Slots",
        "Price",
        "Owner"
    ):

        approved_tree.heading(
            col,
            text=col
        )

        if col == "Google Maps Location":

            approved_tree.column(
                col,
                width=400
            )

        else:

            approved_tree.column(
                col,
                width=170
            )

    approved_tree.pack(
        fill="both",
        expand=True,
        padx=10,
        pady=10
    )

    cursor.execute(
        """
        SELECT
            mall,
            location,
            slots,
            price,
            owner_email
        FROM requests
        WHERE status = 'approved'
        ORDER BY mall
        """
    )

    for row in cursor.fetchall():

        approved_tree.insert(
            "",
            tk.END,
            values=row
        )


# ============================================================
#                    GET APPROVED MALLS
# ============================================================

def get_approved_malls():

    cursor.execute(
        """
        SELECT mall
        FROM requests
        WHERE status = 'approved'
        ORDER BY mall
        """
    )

    return [
        row[0]
        for row in cursor.fetchall()
    ]


# ============================================================
#                    LOAD APPROVED MALLS
# ============================================================

def load_approved_malls():

    malls = get_approved_malls()

    mall_menu["menu"].delete(
        0,
        tk.END
    )

    if not malls:

        selected_mall.set(
            "No approved parking"
        )

        location_label.config(
            text="Google Maps Location: -"
        )

        customer_maps_button.config(
            state="disabled"
        )

        price_label.config(
            text="Price: -"
        )

        slots_count_label.config(
            text="Total Slots: 0"
        )

        clear_customer_slots()

        return

    selected_mall.set(malls[0])

    for mall in malls:

        mall_menu["menu"].add_command(
            label=mall,
            command=lambda value=mall:
            select_customer_mall(value)
        )

    select_customer_mall(malls[0])


# ============================================================
#                    GET MALL INFO
# ============================================================

def get_mall_info(mall):

    cursor.execute(
        """
        SELECT
            mall,
            location,
            slots,
            price
        FROM requests
        WHERE mall = ?
        AND status = 'approved'
        LIMIT 1
        """,
        (mall,)
    )

    return cursor.fetchone()


# ============================================================
#                    SELECT MALL
# ============================================================

def select_customer_mall(mall):

    selected_mall.set(mall)

    update_customer_mall_information()


# ============================================================
#                    CLEAR SLOTS
# ============================================================

def clear_customer_slots():

    global slot_buttons

    slot_buttons = {}

    for widget in slots_frame.winfo_children():

        widget.destroy()


# ============================================================
#                    DATE / TIME
# ============================================================

def get_customer_datetime():

    try:

        day = int(day_var.get())
        month = month_var.get()
        year = int(year_var.get())

        from_hour = int(from_hour_var.get())
        from_minute = int(from_minute_var.get())
        from_ampm = from_ampm_var.get()

        to_hour = int(to_hour_var.get())
        to_minute = int(to_minute_var.get())
        to_ampm = to_ampm_var.get()

        start_text = (
            f"{day} {month} {year} "
            f"{from_hour:02d}:{from_minute:02d} "
            f"{from_ampm}"
        )

        end_text = (
            f"{day} {month} {year} "
            f"{to_hour:02d}:{to_minute:02d} "
            f"{to_ampm}"
        )

        start_dt = datetime.strptime(
            start_text,
            "%d %B %Y %I:%M %p"
        )

        end_dt = datetime.strptime(
            end_text,
            "%d %B %Y %I:%M %p"
        )

        return start_dt, end_dt

    except Exception:

        return None, None


# ============================================================
#                    CHECK SLOT BOOKING
# ============================================================

def is_slot_booked(
    mall,
    slot,
    start_dt,
    end_dt
):

    # Complete expired bookings automatically.

    cursor.execute(
        """
        UPDATE bookings
        SET status = 'completed'
        WHERE end_datetime <= ?
        AND status = 'active'
        """,
        (datetime.now().isoformat(),)
    )

    conn.commit()

    cursor.execute(
        """
        SELECT id
        FROM bookings
        WHERE mall = ?
        AND slot = ?
        AND status = 'active'
        AND start_datetime < ?
        AND end_datetime > ?
        """,
        (
            mall,
            slot,
            end_dt.isoformat(),
            start_dt.isoformat()
        )
    )

    return cursor.fetchone() is not None


# ============================================================
#                    CREATE PARKING SLOTS
# ============================================================

def create_customer_slots(total_slots):

    global selected_customer_slot
    global slot_buttons

    selected_customer_slot = None

    slot_buttons = {}

    clear_customer_slots()

    customer_slot_label.config(
        text="Selected Slot: None"
    )

    columns = 12

    for slot_number in range(
        1,
        total_slots + 1
    ):

        button = tk.Button(
            slots_frame,
            text=f"S{slot_number}",
            width=5,
            height=1,
            font=("Arial", 9),
            relief="raised"
        )

        button.config(
            command=lambda
            s=slot_number,
            b=button:
            select_customer_slot(
                s,
                b
            )
        )

        row = (
            slot_number - 1
        ) // columns

        col = (
            slot_number - 1
        ) % columns

        button.grid(
            row=row,
            column=col,
            padx=2,
            pady=2
        )

        slot_buttons[slot_number] = button


# ============================================================
#                    SELECT PARKING SLOT
# ============================================================

def select_customer_slot(
    slot,
    button=None
):

    global selected_customer_slot

    if button is not None:

        if str(button["state"]) == "disabled":
            return

    selected_customer_slot = slot

    for (
        slot_number,
        btn
    ) in slot_buttons.items():

        if str(btn["state"]) != "disabled":

            btn.config(
                relief="raised"
            )

    if button is not None:

        if str(button["state"]) != "disabled":

            button.config(
                relief="sunken"
            )

    customer_slot_label.config(
        text=f"Selected Slot: S{slot}"
    )


# ============================================================
#                    UPDATE MALL INFORMATION
# ============================================================

def update_customer_mall_information():

    mall = selected_mall.get()

    if (
        not mall or
        mall == "No approved parking"
    ):

        location_label.config(
            text="Google Maps Location: -"
        )

        customer_maps_button.config(
            state="disabled"
        )

        price_label.config(
            text="Price: -"
        )

        slots_count_label.config(
            text="Total Slots: 0"
        )

        clear_customer_slots()

        return

    info = get_mall_info(mall)

    if not info:
        return

    exact_maps_url = info[1]
    slots = info[2]
    price = info[3]

    location_label.config(
        text=(
            "Google Maps Location:\n"
            f"{exact_maps_url}"
        )
    )

    if is_google_maps_url(exact_maps_url):

        customer_maps_button.config(
            state="normal"
        )

    else:

        customer_maps_button.config(
            state="disabled"
        )

    price_label.config(
        text=f"Price: ₹{price:.2f} / minute"
    )

    slots_count_label.config(
        text=f"Total Slots: {slots}"
    )

    create_customer_slots(slots)

    update_booked_slots()


# ============================================================
#                    UPDATE BOOKED SLOTS
# ============================================================

def update_booked_slots():

    mall = selected_mall.get()

    if (
        not mall or
        mall == "No approved parking"
    ):

        return

    start_dt, end_dt = get_customer_datetime()

    if (
        start_dt is None or
        end_dt is None
    ):

        return

    if end_dt <= start_dt:
        return

    for (
        slot_number,
        button
    ) in slot_buttons.items():

        if is_slot_booked(
            mall,
            slot_number,
            start_dt,
            end_dt
        ):

            button.config(
                state="disabled",
                text=f"S{slot_number}\nBooked"
            )

        else:

            button.config(
                state="normal",
                text=f"S{slot_number}"
            )


# ============================================================
#                    BOOK PARKING
# ============================================================

def book_customer_slot():

    global selected_customer_slot

    name = customer_name_entry.get().strip()
    email = customer_email_entry.get().strip()
    vehicle = vehicle_entry.get().strip()

    mall = selected_mall.get()

    if not name:

        messagebox.showerror(
            "Missing Name",
            "Please enter customer name."
        )

        return

    if not valid_email(email):

        messagebox.showerror(
            "Invalid Email",
            "Please enter a valid customer email."
        )

        return

    if not vehicle:

        messagebox.showerror(
            "Missing Vehicle Number",
            "Please enter vehicle number."
        )

        return

    if (
        not mall or
        mall == "No approved parking"
    ):

        messagebox.showerror(
            "No Parking",
            "Please select an approved mall."
        )

        return

    if selected_customer_slot is None:

        messagebox.showerror(
            "Select Slot",
            "Please select a parking slot."
        )

        return

    start_dt, end_dt = get_customer_datetime()

    if (
        start_dt is None or
        end_dt is None
    ):

        messagebox.showerror(
            "Invalid Date/Time",
            "Please select a valid date and time."
        )

        return

    if end_dt <= start_dt:

        messagebox.showerror(
            "Invalid Time",
            "To time must be after From time."
        )

        return

    if start_dt < datetime.now():

        messagebox.showerror(
            "Invalid Date",
            "You cannot make a booking in the past."
        )

        return

    if is_slot_booked(
        mall,
        selected_customer_slot,
        start_dt,
        end_dt
    ):

        messagebox.showwarning(
            "Slot Unavailable",
            f"S{selected_customer_slot} is already "
            "booked for this time."
        )

        update_booked_slots()

        return

    info = get_mall_info(mall)

    if not info:

        messagebox.showerror(
            "Error",
            "Mall information not found."
        )

        return

    exact_maps_url = info[1]

    if not is_google_maps_url(exact_maps_url):

        messagebox.showerror(
            "Location Error",
            "The approved mall does not have a valid "
            "Google Maps location."
        )

        return

    price_per_minute = float(info[3])

    duration_seconds = (
        end_dt - start_dt
    ).total_seconds()

    duration_minutes = (
        duration_seconds / 60
    )

    total_cost = (
        duration_minutes *
        price_per_minute
    )

    cursor.execute(
        """
        INSERT INTO bookings
        (
            customer_name,
            customer_email,
            vehicle,
            mall,
            slot,
            start_datetime,
            end_datetime,
            price_per_minute,
            total_cost,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (
            name,
            email,
            vehicle,
            mall,
            selected_customer_slot,
            start_dt.isoformat(),
            end_dt.isoformat(),
            price_per_minute,
            total_cost
        )
    )

    conn.commit()

    booking_id = cursor.lastrowid

    body = f"""
SMART PARKING PLATFORM

BOOKING CONFIRMATION
============================

Booking ID:
#{booking_id}

Customer:
{name}

Email:
{email}

Vehicle Number:
{vehicle}

Mall:
{mall}

Exact Google Maps Location:
{exact_maps_url}

Parking Slot:
S{selected_customer_slot}

Date:
{start_dt.strftime("%d %B %Y")}

From:
{start_dt.strftime("%I:%M %p")}

To:
{end_dt.strftime("%I:%M %p")}

Duration:
{duration_minutes:.2f} minutes

Price:
₹{price_per_minute:.2f} / minute

TOTAL COST:
₹{total_cost:.2f}

============================

Thank you for using
Smart Parking Platform.
"""

    email_success = send_email(
        email,
        "Smart Parking - Booking Confirmation",
        body
    )

    booked_slot = selected_customer_slot

    if email_success:

        messagebox.showinfo(
            "Booking Successful",
            f"Booking confirmed!\n\n"
            f"Booking ID: #{booking_id}\n"
            f"Mall: {mall}\n"
            f"Slot: S{booked_slot}\n"
            f"Total: ₹{total_cost:.2f}\n\n"
            f"Confirmation email sent."
        )

    else:

        messagebox.showwarning(
            "Booking Successful",
            f"Booking confirmed!\n\n"
            f"Booking ID: #{booking_id}\n"
            f"Slot: S{booked_slot}\n"
            f"Total: ₹{total_cost:.2f}\n\n"
            f"Email could not be sent."
        )

    selected_customer_slot = None

    customer_slot_label.config(
        text="Selected Slot: None"
    )

    customer_name_entry.delete(
        0,
        tk.END
    )

    customer_email_entry.delete(
        0,
        tk.END
    )

    vehicle_entry.delete(
        0,
        tk.END
    )

    update_customer_mall_information()


# ============================================================
#                    FIXED REFRESH SYSTEM
# ============================================================

def refresh_application():

    global refresh_job

    try:

        # Refresh current mall and slot information
        update_customer_mall_information()

        # Schedule exactly ONE next refresh
        refresh_job = root.after(
            30000,
            refresh_application
        )

    except tk.TclError:

        # Window is already closing
        refresh_job = None


def start_refresh():

    global refresh_job

    # Prevent duplicate scheduled callbacks
    if refresh_job is None:

        refresh_job = root.after(
            30000,
            refresh_application
        )


def stop_refresh():

    global refresh_job

    if refresh_job is not None:

        try:

            root.after_cancel(
                refresh_job
            )

        except tk.TclError:
            pass

        refresh_job = None


# ============================================================
#                    MAIN WINDOW
# ============================================================

root = tk.Tk()

root.title(
    "Smart Parking Platform"
)

root.geometry(
    "1250x900"
)

root.minsize(
    1000,
    700
)


# ============================================================
#                    MAIN TITLE
# ============================================================

tk.Label(
    root,
    text="SMART PARKING PLATFORM",
    font=("Arial", 28, "bold")
).pack(
    pady=15
)


# ============================================================
#                    OWNER FRAME
# ============================================================

owner_frame = tk.LabelFrame(
    root,
    text="Shopping Mall Owner",
    font=("Arial", 15, "bold")
)

owner_frame.pack(
    fill="x",
    padx=25,
    pady=8
)


tk.Label(
    owner_frame,
    text="Owner Email"
).grid(
    row=0,
    column=0,
    padx=10,
    pady=8
)


owner_email_entry = tk.Entry(
    owner_frame,
    width=30
)

owner_email_entry.grid(
    row=0,
    column=1,
    padx=10,
    pady=8
)


tk.Label(
    owner_frame,
    text="Password"
).grid(
    row=0,
    column=2,
    padx=10,
    pady=8
)


owner_password_entry = tk.Entry(
    owner_frame,
    width=25,
    show="*"
)

owner_password_entry.grid(
    row=0,
    column=3,
    padx=10,
    pady=8
)


tk.Button(
    owner_frame,
    text="Login / Register",
    command=owner_login_register,
    width=17
).grid(
    row=0,
    column=4,
    padx=10
)


tk.Button(
    owner_frame,
    text="Send OTP",
    command=send_owner_otp,
    width=15
).grid(
    row=1,
    column=1,
    padx=10,
    pady=5
)


owner_otp_entry = tk.Entry(
    owner_frame,
    width=30
)

owner_otp_entry.grid(
    row=1,
    column=2,
    padx=10,
    pady=5
)


tk.Button(
    owner_frame,
    text="Verify OTP",
    command=verify_owner_otp,
    width=15
).grid(
    row=1,
    column=3,
    padx=10
)


owner_status_label = tk.Label(
    owner_frame,
    text="Not logged in",
    fg="red",
    font=("Arial", 11, "bold")
)

owner_status_label.grid(
    row=2,
    column=0,
    columnspan=5,
    pady=5
)


# ============================================================
#                    REQUEST FRAME
# ============================================================

request_frame = tk.LabelFrame(
    root,
    text="Add Parking Request",
    font=("Arial", 15, "bold")
)

request_frame.pack(
    fill="x",
    padx=25,
    pady=8
)


tk.Label(
    request_frame,
    text="Mall Name"
).grid(
    row=0,
    column=0,
    padx=10,
    pady=8
)


mall_entry = tk.Entry(
    request_frame,
    width=25
)

mall_entry.grid(
    row=0,
    column=1,
    padx=10,
    pady=8
)


tk.Label(
    request_frame,
    text="Exact Google Maps Link"
).grid(
    row=0,
    column=2,
    padx=10,
    pady=8
)


location_entry = tk.Entry(
    request_frame,
    width=50
)

location_entry.grid(
    row=0,
    column=3,
    padx=10,
    pady=8
)


tk.Button(
    request_frame,
    text="📍 Open Exact Location",
    command=open_location_in_google_maps,
    width=22
).grid(
    row=0,
    column=4,
    padx=8,
    pady=8
)


tk.Label(
    request_frame,
    text=(
        "Paste the exact Google Maps link of the mall "
        "(https://www.google.com/maps/... "
        "or https://maps.app.goo.gl/...)"
    ),
    fg="gray",
    font=("Arial", 9)
).grid(
    row=1,
    column=2,
    columnspan=3,
    padx=10,
    sticky="w"
)


tk.Label(
    request_frame,
    text="Total Slots"
).grid(
    row=2,
    column=0,
    padx=10,
    pady=8
)


slots_entry = tk.Entry(
    request_frame,
    width=25
)

slots_entry.grid(
    row=2,
    column=1,
    padx=10,
    pady=8
)


tk.Label(
    request_frame,
    text="Price / Minute"
).grid(
    row=2,
    column=2,
    padx=10,
    pady=8
)


price_entry = tk.Entry(
    request_frame,
    width=25
)

price_entry.grid(
    row=2,
    column=3,
    padx=10,
    pady=8
)


tk.Button(
    request_frame,
    text="Send Parking Request",
    command=send_parking_request,
    width=22
).grid(
    row=3,
    column=1,
    columnspan=2,
    pady=10
)


tk.Button(
    request_frame,
    text="Admin Panel",
    command=admin_panel,
    bg="orange",
    width=15
).grid(
    row=3,
    column=3,
    pady=10
)


# ============================================================
#                    CUSTOMER OUTER FRAME
# ============================================================

customer_outer_frame = tk.LabelFrame(
    root,
    text="Customer Parking Booking",
    font=("Arial", 15, "bold")
)

customer_outer_frame.pack(
    fill="both",
    expand=True,
    padx=25,
    pady=8
)


# ============================================================
#                    SCROLLABLE AREA
# ============================================================

canvas = tk.Canvas(
    customer_outer_frame,
    highlightthickness=0
)

scrollbar = ttk.Scrollbar(
    customer_outer_frame,
    orient="vertical",
    command=canvas.yview
)

canvas.configure(
    yscrollcommand=scrollbar.set
)

scrollbar.pack(
    side="right",
    fill="y"
)

canvas.pack(
    side="left",
    fill="both",
    expand=True
)


customer_frame = tk.Frame(
    canvas
)

canvas_window = canvas.create_window(
    (0, 0),
    window=customer_frame,
    anchor="nw"
)


def configure_scroll_region(event=None):

    canvas.configure(
        scrollregion=canvas.bbox("all")
    )


customer_frame.bind(
    "<Configure>",
    configure_scroll_region
)


def configure_canvas_width(event):

    canvas.itemconfig(
        canvas_window,
        width=event.width
    )


canvas.bind(
    "<Configure>",
    configure_canvas_width
)


def mouse_wheel(event):

    canvas.yview_scroll(
        int(-1 * (event.delta / 120)),
        "units"
    )


canvas.bind_all(
    "<MouseWheel>",
    mouse_wheel
)


# ============================================================
#                    CUSTOMER MALL
# ============================================================

tk.Label(
    customer_frame,
    text="Select Parking Mall",
    font=("Arial", 13, "bold")
).pack(
    pady=8
)


selected_mall = tk.StringVar(
    value="No approved parking"
)


mall_menu = tk.OptionMenu(
    customer_frame,
    selected_mall,
    "No approved parking"
)

mall_menu.config(
    width=30,
    font=("Arial", 11)
)

mall_menu.pack(
    pady=5
)


# ============================================================
#                    CUSTOMER LOCATION
# ============================================================

tk.Label(
    customer_frame,
    text="Saved Mall Location",
    font=("Arial", 12, "bold")
).pack(
    pady=(8, 2)
)


location_label = tk.Label(
    customer_frame,
    text="Google Maps Location: -",
    font=("Arial", 10),
    wraplength=1000,
    justify="center"
)

location_label.pack(
    pady=3
)


customer_maps_button = tk.Button(
    customer_frame,
    text="📍 Open Exact Mall Location in Google Maps",
    command=open_customer_location,
    state="disabled",
    font=("Arial", 10, "bold")
)

customer_maps_button.pack(
    pady=5
)


price_label = tk.Label(
    customer_frame,
    text="Price: -",
    font=("Arial", 11)
)

price_label.pack(
    pady=3
)


slots_count_label = tk.Label(
    customer_frame,
    text="Total Slots: 0",
    font=("Arial", 11)
)

slots_count_label.pack(
    pady=3
)


# ============================================================
#                    CUSTOMER DETAILS
# ============================================================

tk.Label(
    customer_frame,
    text="Customer Details",
    font=("Arial", 13, "bold")
).pack(
    pady=8
)


customer_info_frame = tk.Frame(
    customer_frame
)

customer_info_frame.pack(
    pady=5
)


tk.Label(
    customer_info_frame,
    text="Customer Name"
).grid(
    row=0,
    column=0,
    padx=5
)


customer_name_entry = tk.Entry(
    customer_info_frame,
    width=20
)

customer_name_entry.grid(
    row=0,
    column=1,
    padx=5
)


tk.Label(
    customer_info_frame,
    text="Email"
).grid(
    row=0,
    column=2,
    padx=5
)


customer_email_entry = tk.Entry(
    customer_info_frame,
    width=28
)

customer_email_entry.grid(
    row=0,
    column=3,
    padx=5
)


tk.Label(
    customer_info_frame,
    text="Vehicle No."
).grid(
    row=0,
    column=4,
    padx=5
)


vehicle_entry = tk.Entry(
    customer_info_frame,
    width=18
)

vehicle_entry.grid(
    row=0,
    column=5,
    padx=5
)


# ============================================================
#                    DATE
# ============================================================

date_frame = tk.Frame(
    customer_frame
)

date_frame.pack(
    pady=7
)


tk.Label(
    date_frame,
    text="Date"
).grid(
    row=0,
    column=0,
    padx=5
)


day_var = tk.StringVar(
    value=str(datetime.now().day)
)


ttk.Combobox(
    date_frame,
    textvariable=day_var,
    values=[
        str(i)
        for i in range(1, 32)
    ],
    width=5,
    state="readonly"
).grid(
    row=0,
    column=1,
    padx=3
)


month_var = tk.StringVar(
    value=datetime.now().strftime("%B")
)


ttk.Combobox(
    date_frame,
    textvariable=month_var,
    values=[
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December"
    ],
    width=12,
    state="readonly"
).grid(
    row=0,
    column=2,
    padx=3
)


year_var = tk.StringVar(
    value=str(datetime.now().year)
)


ttk.Combobox(
    date_frame,
    textvariable=year_var,
    values=[
        str(datetime.now().year + i)
        for i in range(5)
    ],
    width=7,
    state="readonly"
).grid(
    row=0,
    column=3,
    padx=3
)


# ============================================================
#                    TIME
# ============================================================

time_frame = tk.Frame(
    customer_frame
)

time_frame.pack(
    pady=5
)


tk.Label(
    time_frame,
    text="From"
).grid(
    row=0,
    column=0,
    padx=5
)


from_hour_var = tk.StringVar(
    value="10"
)


ttk.Combobox(
    time_frame,
    textvariable=from_hour_var,
    values=[
        f"{i:02d}"
        for i in range(1, 13)
    ],
    width=5,
    state="readonly"
).grid(
    row=0,
    column=1
)


from_minute_var = tk.StringVar(
    value="00"
)


ttk.Combobox(
    time_frame,
    textvariable=from_minute_var,
    values=[
        f"{i:02d}"
        for i in range(60)
    ],
    width=5,
    state="readonly"
).grid(
    row=0,
    column=2
)


from_ampm_var = tk.StringVar(
    value="AM"
)


ttk.Combobox(
    time_frame,
    textvariable=from_ampm_var,
    values=[
        "AM",
        "PM"
    ],
    width=5,
    state="readonly"
).grid(
    row=0,
    column=3
)


tk.Label(
    time_frame,
    text="To"
).grid(
    row=1,
    column=0,
    padx=5,
    pady=5
)


to_hour_var = tk.StringVar(
    value="11"
)


ttk.Combobox(
    time_frame,
    textvariable=to_hour_var,
    values=[
        f"{i:02d}"
        for i in range(1, 13)
    ],
    width=5,
    state="readonly"
).grid(
    row=1,
    column=1
)


to_minute_var = tk.StringVar(
    value="00"
)


ttk.Combobox(
    time_frame,
    textvariable=to_minute_var,
    values=[
        f"{i:02d}"
        for i in range(60)
    ],
    width=5,
    state="readonly"
).grid(
    row=1,
    column=2
)


to_ampm_var = tk.StringVar(
    value="AM"
)


ttk.Combobox(
    time_frame,
    textvariable=to_ampm_var,
    values=[
        "AM",
        "PM"
    ],
    width=5,
    state="readonly"
).grid(
    row=1,
    column=3
)


# ============================================================
#                    PARKING SLOTS
# ============================================================

tk.Label(
    customer_frame,
    text="Available Parking Slots",
    font=("Arial", 13, "bold")
).pack(
    pady=8
)


slots_frame = tk.Frame(
    customer_frame
)

slots_frame.pack(
    pady=5
)


customer_slot_label = tk.Label(
    customer_frame,
    text="Selected Slot: None",
    font=("Arial", 12, "bold")
)

customer_slot_label.pack(
    pady=8
)


# ============================================================
#                    BOOK BUTTON
# ============================================================

tk.Button(
    customer_frame,
    text="BOOK PARKING",
    command=book_customer_slot,
    bg="green",
    fg="white",
    font=("Arial", 13, "bold"),
    width=25,
    height=2
).pack(
    pady=15
)


# ============================================================
#                    INITIAL LOAD
# ============================================================

load_approved_malls()


# ============================================================
#                    START ONE REFRESH JOB
# ============================================================

start_refresh()


# ============================================================
#                    CLOSE APPLICATION
# ============================================================

def close_application():

    # First cancel the scheduled refresh.
    stop_refresh()

    try:

        conn.commit()
        conn.close()

    except Exception:

        pass

    root.destroy()


root.protocol(
    "WM_DELETE_WINDOW",
    close_application
)


# ============================================================
#                    START APPLICATION
# ============================================================

root.mainloop()
