[README.md.md](https://github.com/user-attachments/files/34869992/README.md.md)
# 🅿️ Smart Parking Platform

A desktop application built with **Python, Tkinter and SQLite** that connects **shopping mall owners** who have spare parking space with **customers** who want to reserve a parking slot for a specific time.

Owners list their parking, an admin approves it, and customers book individual slots by the minute. Everyone is kept informed through automatic emails.

---

## 📑 Table of Contents

1. [Problem Statement](#-problem-statement)
2. [Features](#-features)
3. [How It Works](#-how-it-works)
4. [Tech Stack](#-tech-stack)
5. [Installation & Setup](#-installation--setup)
6. [How to Use](#-how-to-use)
7. [Database Design](#-database-design)
8. [Validation & Business Rules](#-validation--business-rules)
9. [Project Structure](#-project-structure)
10. [Known Limitations](#-known-limitations)
11. [Future Improvements](#-future-improvements)
12. [Screenshots](#-screenshots)
13. [Author](#-author)

---

## 🎯 Problem Statement

Finding parking near shopping malls is time-consuming, and mall owners have no easy way to rent out unused parking space. This project provides a simple platform where:

- **Owners** can list their parking area with the number of slots and a price per minute.
- **An admin** reviews each listing so only genuine parking spaces appear.
- **Customers** can see the exact location on Google Maps, check which slots are free for their time window, and book instantly.

---

## ✨ Features

### 👤 Mall Owner
- Register / log in with email and password
- **Two-step login**: password check + a 6-digit **OTP sent by email** (valid for 5 minutes)
- Submit a parking request with mall name, Google Maps link, total slots and price per minute
- Receive an email when the request is **approved or rejected**

### 🛡️ Admin
- View all parking requests (newest first) in a table
- **Approve** or **Reject** a request with one click
- See the list of all approved parking locations
- Gets an email notification whenever a new request is submitted

### 🚗 Customer
- Choose from the list of **approved malls**
- Open the mall's exact location in **Google Maps** with one click
- Pick a date and a **From / To** time
- See a **visual grid of slots** (S1, S2, …) – already-booked slots are greyed out and marked *Booked*
- Get the **total cost** calculated automatically and a **confirmation email**

### ⚙️ System
- Prevents **double booking** of the same slot for overlapping times
- Automatically marks finished bookings as *completed*
- Slot availability **auto-refreshes every 30 seconds**
- Database tables and columns are **created / migrated automatically** on first run

---

## 🔄 How It Works

```
 Mall Owner                    Admin                       Customer
     │                           │                             │
     │ 1. Register / Login       │                             │
     │ 2. Verify email OTP       │                             │
     │ 3. Submit parking request │                             │
     │──────────────────────────▶│ (email notification)        │
     │                           │ 4. Approve / Reject         │
     │◀──────────────────────────│ (email to owner)            │
     │                           │                             │
     │                           │        5. Select approved mall
     │                           │        6. Choose date & time
     │                           │        7. Pick a free slot
     │                           │        8. Book ◀────────────│
     │                           │           (confirmation email with total cost)
```

---

## 🧰 Tech Stack

| Area | Technology |
|------|-----------|
| Language | Python 3 |
| GUI | Tkinter (`tk`, `ttk`) |
| Database | SQLite (`sqlite3`) |
| Email | Gmail SMTP over SSL (`smtplib`, `ssl`) |
| Maps | Google Maps links opened via `webbrowser` |

No third-party libraries are required – everything comes from the Python standard library.

---

## 🚀 Installation & Setup

### Prerequisites
- **Python 3.8+**
- **Tkinter** (included with the Python installer on Windows and macOS; on Linux run `sudo apt install python3-tk`)
- A **Gmail account** with an **App Password** (used to send emails)

### Step 1 – Get the code
```bash
git clone https://github.com/<your-username>/smart-parking-platform.git
cd smart-parking-platform
```

### Step 2 – Create a Gmail App Password
1. Open your Google Account → **Security**
2. Turn on **2-Step Verification**
3. Search for **App passwords** and create one (name it e.g. "Smart Parking")
4. Copy the 16-character password

### Step 3 – Set environment variables
The email credentials are **not stored in the code** for security.

**Windows (PowerShell)**
```powershell
$env:PARKING_ADMIN_EMAIL = "your-email@gmail.com"
$env:PARKING_APP_PASSWORD = "your app password"
```

**Windows (Command Prompt)**
```cmd
set PARKING_ADMIN_EMAIL=your-email@gmail.com
set PARKING_APP_PASSWORD=your app password
```

**macOS / Linux**
```bash
export PARKING_ADMIN_EMAIL="your-email@gmail.com"
export PARKING_APP_PASSWORD="your app password"
```

### Step 4 – Run
```bash
python Smart_Parking_Platform.py
```
The database file `parking.db` is created automatically in the same folder.

---

## 📖 How to Use

### As a Mall Owner
1. Enter your **email and password** and click **Login / Register** (new emails are registered automatically).
2. Click **Send OTP**, check your email, type the code and click **Verify OTP**.
3. In **Add Parking Request**, fill in:
   - Mall name
   - Exact Google Maps link (`https://www.google.com/maps/...` or `https://maps.app.goo.gl/...`)
   - Total slots
   - Price per minute (₹)
4. Click **Send Parking Request**. Use **Open Exact Location** first to check your link.

### As the Admin
1. Click **Admin Panel**.
2. Select a request in the table and click **APPROVE** or **REJECT**.
3. The owner is emailed and approved malls become visible to customers.

### As a Customer
1. Scroll to **Customer Parking Booking** and choose a mall.
2. Enter your name, email and vehicle number.
3. Select the date and the From / To time.
4. Click a free slot (it shows as pressed), then click **BOOK PARKING**.
5. Check your email for the booking confirmation.

---

## 🗄️ Database Design

SQLite database: `parking.db`

**owners**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| email | TEXT | Unique |
| password | TEXT | Owner password |

**requests**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| owner_email | TEXT | Who submitted it |
| mall | TEXT | Mall name |
| location | TEXT | Google Maps URL |
| slots | INTEGER | Total parking slots |
| price | REAL | Price per minute |
| status | TEXT | `pending`, `approved` or `rejected` |

**bookings**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key (booking ID) |
| customer_name | TEXT | |
| customer_email | TEXT | |
| vehicle | TEXT | Vehicle number |
| mall | TEXT | |
| slot | INTEGER | Slot number |
| start_datetime | TEXT | ISO format |
| end_datetime | TEXT | ISO format |
| price_per_minute | REAL | Price locked at booking time |
| total_cost | REAL | Duration × price per minute |
| status | TEXT | `active` or `completed` |

---

## ✅ Validation & Business Rules

- **Email** must match a valid format.
- **Google Maps link** must be `https` and from `google.com/maps`, `maps.google.com`, `maps.app.goo.gl` or `goo.gl`.
- **Slots** must be a positive whole number; **price** must be a positive number.
- Duplicate pending/approved requests for the same mall and location are blocked.
- **OTP** expires after **5 minutes**.
- A booking's **end time must be after its start time** and cannot be **in the past**.
- A slot cannot be booked if another active booking **overlaps** the chosen time.
- **Total cost** = `(duration in minutes) × (price per minute)`.

---

## 📂 Project Structure

```
smart-parking-platform/
├── Smart_Parking_Platform.py   # Complete application (GUI + logic + database)
├── README.md                   # Project documentation
├── requirements.txt            # Dependencies (none needed)
├── .gitignore                  # Keeps parking.db and secrets out of Git
└── parking.db                  # Created automatically on first run (not in Git)
```

---

## ⚠️ Known Limitations

- Owner passwords are stored in **plain text** (should be hashed).
- The **Admin Panel button is not password-protected**; anyone using the app can open it.
- A booking covers **one day only** (single date with From / To times).
- Single-computer application: the SQLite database is local, so it is not shared between users on different machines.
- Booked slots are matched by **mall name**, so two approved malls should not share the same name.

---

## 🔮 Future Improvements

- Hash passwords (e.g. `bcrypt`) and add a separate admin login
- Online payment integration (UPI / cards)
- Cancel or modify bookings
- Booking history for customers and earnings dashboard for owners
- Move to a web or mobile app with a shared server database (Flask / Django + PostgreSQL)
- Automatic slot pricing based on demand

---

## 🖼️ Screenshots

> Add screenshots of the app here, for example:
>
> `![Main window](screenshots/main.png)`
> `![Admin panel](screenshots/admin.png)`
> `![Slot booking](screenshots/booking.png)`

---

## 👨‍💻 Author

**Chandu**
Chemical Engineering student, IIT Madras

---

*Built as a project to learn GUI development, database design and email automation in Python.*
