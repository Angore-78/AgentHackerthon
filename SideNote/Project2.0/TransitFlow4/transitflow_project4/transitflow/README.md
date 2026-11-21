# TransitFlow — Django Goods-in-Transit & Cold-Chain Logistics Web Application

TransitFlow is a comprehensive Django web application designed to track and record products in transit across regional logistics corridors. It incorporates distinct operational portals for **Managers**, **Porters**, **Drivers**, and **Clients**, with strict role-based session management, automated cold-chain monitoring for **Perishable** versus **Non-Perishable** cargo, a privilege-scoped **AI Chatbot** assistant, and an integrated **PayHero Kenya Lipwa Link / STK Push** payment engine.

---

## 🌟 Key Capabilities & Features

### 1. Perishable vs. Non-Perishable Goods Separation
- **Perishable Cargo Management**:
  - Defined safe core temperature ranges (e.g. 2.0°C to 6.0°C for fresh produce, 1.0°C to 4.0°C for dairy).
  - Continuous refrigeration requirement tracking (`requires_refrigeration`).
  - Spoilage risk classification (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  - Shelf-life countdown and storage humidity requirements.
  - **Automated Cold-Chain Violation Detection**: When a Porter or Driver records an infrared temperature check outside the cargo's permissible limits, the system automatically flags `is_temp_breach = True`, sets the shipment status to `TEMP_ALERT`, and alerts fleet managers.
- **Non-Perishable Cargo Management**:
  - Fragility indicators (`is_fragile`), hazardous materials classification (`is_hazardous`), stackable stowage rules (`stackable`), and custom handling instructions.

---

### 2. Four Isolated Role Portals with Distinct Sessions
Each user role operates within an isolated portal environment protected by `RoleSessionMiddleware` and `@role_required` guards:

| Portal Role | Access URL | Session Timeout Policy | Primary Responsibilities |
|---|---|---|---|
| **Manager** | `/portal/manager/` | **4 Hours** (High Security Admin Window) | Fleet-wide analytics, consignment dispatch, vehicle assignment, perishable alert monitoring, PayHero API credentials. |
| **Porter** | `/portal/porter/` | **10 Hours** (Warehouse Shift) | Depot cargo receiving, cold-room check-in, infrared temperature verification, tamper seal audits, loading manifests. |
| **Driver** | `/portal/driver/` | **12 Hours** (Road Transit Shift) | Active vehicle manifest, highway route checkpoints (Mtito Andei, Naivasha, Salama, etc.), delay logging, delivery sign-off. |
| **Client** | `/portal/client/` | **7 Days** (Customer Convenience) | Track own shipments in real-time, inspect cold-chain preservation status, book new consignments, settle invoices via PayHero. |

> **Security & Isolation:** If a Driver or Client attempts to navigate directly to `/portal/manager/`, the session middleware intercepts the request, blocks unauthorized traversal, and redirects the user back to their designated portal with an access notice.

---

### 3. Privilege-Scoped Dashboard Chatbot Assistant
Built directly into the bottom-right of every dashboard view:
- **Client Clearance**: Can **only** query information about shipments and products belonging to their account. If they attempt to inspect company financials or other clients' goods, the assistant gracefully restricts access.
- **Driver Clearance**: Can query their vehicle manifest, assigned cargo items, cold-chain temperature thresholds, and route checkpoints.
- **Porter Clearance**: Can query depot handling checklists, cold-room storage rules, fragile item stowage, and temperature inspection protocols.
- **Manager Clearance**: Has unrestricted clearance to ask for executive fleet summaries, temperature breach counts, revenue, and driver availability.
- **Interactive UI**: Includes dynamic suggested prompt chips, markdown message rendering, and a real-time REST API endpoint (`/assistant/api/message/`).

---

### 4. PayHero Lipwa Link & STK Push Payment Section
TransitFlow integrates Kenya's **PayHero** payment gateway (`backend.payhero.co.ke`) to handle freight and delivery charges:
- **Dynamic Lipwa Link Generation**:
  Constructs pre-filled checkout URLs:
  ```text
  https://lipwa.link/{slug}?amount=3500&phone=254712345678&name=JohnDoe&channel_id=133&reference=PAY-TF-123456&success_url=...&failed_url=...
  ```
- **Programmatic M-Pesa STK Push**:
  Dispatches payment requests directly to customer mobile devices via `POST https://backend.payhero.co.ke/api/v2/payments` with Basic Authentication.
- **Webhook Callback Processing (`/payments/callback/`)**:
  Receives asynchronous confirmation from PayHero, verifies transaction reference, saves M-Pesa receipt code, and marks `Shipment.is_paid = True`.
- **Built-in Mock Sandbox Simulator**:
  Allows zero-cost demonstration and automated unit testing without real money by simulating instantaneous M-Pesa approvals.
- **PayHero Lipwa Link Integration via Chatbot & Portal**:
  Clients can make payments directly through PayHero Lipwa Links generated dynamically on-the-fly inside the chat assistant or through the customer billing portal.
- **Dedicated Standalone Developer Manual (`PayHero_Lipwa_Link_Guide.pdf`)**:
  Exported developer manual explaining PayHero registration, channel linking, API keys, payload structures, parameters table, and troubleshooting.

---

## 🏛️ Choice of Implementation & Architecture

```
transitflow/
├── manage.py
├── seed_demo_data.py            # Populates sample hubs, products, shipments, & users
├── transitflow_project/         # Django project configuration & master URLs
├── core/                        # Custom User model, RoleSessionMiddleware, & Auth
├── logistics/                   # Shipments, Perishable/Non-Perishable Products, Checkpoints
├── payments/                    # PayHero service, Lipwa Link generator, Callback webhook
├── assistant/                   # Privilege-scoped AI Chatbot engine
└── templates/                   # Tailwind CSS responsive templates & Chatbot widget
```

### Architectural Decisions
1. **Custom User Model with Role Inheritance (`core.models.User`)**:
   Extending `AbstractUser` ensures clean database-level role assignment (`MANAGER`, `PORTER`, `DRIVER`, `CLIENT`) with indexed foreign key relationships.
2. **Session-Level Role Pinned Lifespans (`core.middleware.RoleSessionMiddleware`)**:
   Rather than applying a uniform session timeout, the middleware tailors session longevity according to operational requirements:
   - Managers expire after 4 hours to reduce risk on unattended terminals.
   - Drivers and Porters retain active sessions across entire 10-12 hour work shifts.
   - Clients retain comfortable 7-day persistent tracking sessions.
3. **Cold-Chain Excursion Engine (`logistics.models.TransitEvent.save()`)**:
   Automating temperature threshold checks on the model level ensures that whenever any temperature reading is saved—whether through the Porter portal, Driver portal, or API—a breach is caught immediately without relying on manual user vigilance.
4. **PayHero Abstraction Service (`payments.services.PayHeroService`)**:
   Isolates HTTP communication, Basic Auth encoding, phone normalization (`254...`), and Lipwa link generation into a reusable service layer, decoupling billing logic from view presentation.

---

## 🚀 Setup & Execution Guide

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.13)
- SQLite3 (included with Python)

### 2. Virtual Environment & Dependencies
```bash
cd /path/to/ProjectHackerthon

# Create and activate a virtual environment (skip creation if one already exists)
python3 -m venv .venv
source .venv/bin/activate

# Install the project dependencies
python -m pip install -r transitflow/requirements.txt

# Enter the Django project directory
cd transitflow
```

### 3. Database Migration & Seed Demo Data
```bash
# Apply database migrations
python manage.py migrate

# Populate sample data (Users, Hubs, Perishables, Shipments, PayHero settings)
python seed_demo_data.py
```

### 4. Run the Development Server
```bash
python manage.py runserver 0.0.0.0:8000
```
Open your browser and navigate to: **`http://localhost:8000`**

---

## 🔑 Demo Login Accounts

All pre-seeded demo accounts share the password: **`password123`**

| Role | Username | Password | Purpose / Focus |
|---|---|---|---|
| **Operations Manager** | `manager_alice` | `password123` | Full fleet oversight, create products, dispatch shipments, API config. |
| **Depot Porter** | `porter_brian` | `password123` | Cargo receiving, infrared temperature checks, cold-room checklists. |
| **Transit Driver** | `driver_david` | `password123` | Vehicle `KDF 420X`, highway checkpoints, reefer trailer monitoring. |
| **Client Consignor** | `client_cynthia` | `password123` | Track Savannah Fresh produce, PayHero Lipwa Link payment. |
| **Super Administrator** | `admin` | `admin123` | Django Admin Console at `/admin/`. |

> **Pro Tip:** You can also use the **"Switch Role"** dropdown located in the top navigation bar to instantaneously toggle between roles during testing without having to re-authenticate!

---

## 🧪 Running Automated Unit Tests
To run the automated test suite verifying product separation, temperature alerts, role isolation, chatbot privilege scoping, and PayHero Lipwa link generation:

```bash
python manage.py test logistics
```

---

## 📖 PayHero Integration Documentation
- **Developer Guide PDF:** See **`PayHero_Lipwa_Link_Guide.pdf`** accompanying this project for complete architectural flows, endpoint specifications, and query parameter tables.
- **PayHero API Configuration:** Access **`http://localhost:8000/payments/configure/`** (Manager role required) to update Channel IDs, API credentials, and toggle between Sandbox Simulation and Live Production.
