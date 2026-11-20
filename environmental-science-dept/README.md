# Greenwood State University - Department of Environmental Science Website

A modern, responsive, and feature-rich departmental web portal built for the **Department of Environmental Science** at **Greenwood State University**.

## 🌟 Key Features & Requirements Addressed

### 1. Simple & Intuitive Navigation Bar
- **Department Administration**: Quick navigation link that navigates to the leadership and administrative roster (Chairs, Undergraduate/Graduate Directors, Advisors, Lab Coordinators).
- **University Student Portal Link**: Distinctly highlighted CTA button that provides access to the university's Single Sign-On (SSO) Student Portal (with active course schedule, lab safety badging, and Canvas LMS links).
- **Programs Offered**: Direct link to the department's academic degree portfolio (Undergraduate B.S., Graduate M.S. and Ph.D., Minors, and GIS Certificates).
- **Related Events & Seminars**: Direct link to upcoming guest lectures, field excursions, symposia, and workshops with an integrated RSVP workflow.
- **Campus Location & Facilities**: Direct link to the campus locator and Hall 4B floorplan.
- **Mobile Responsive Drawer**: Clean hamburger menu for mobile and tablet devices.

### 2. Default Home Page Highlights
- **Department Head Feature**:
  - Full profile of **Dr. Elena Vance, Ph.D.** (Chair & Lead Investigator).
  - Welcome message on the department's mission, research grants, and student mentorship.
  - Office location (Suite 210-A, BioSciences & Earth Hall 4B), direct email, and weekly office hours.
  - Interactive meeting scheduling trigger.
- **Campus Location & Directions**:
  - Location: **BioSciences & Earth Complex, Hall 4B, 2nd Floor, Suite 210, North Campus**.
  - Interactive Campus Locator with dual modes: **North Campus Quad Map** and **Hall 4B Floorplan Directory**.
  - Transit and parking guide (Campus Shuttle Blue/Green lines, Visitor Lot C, bicycle corrals, and ADA accessibility).
- **Research Pillars & Metrics**:
  - Highlights national ranking (#4 in Eco-Research), 48+ active research labs/field stations, and 96% career placement rate.

### 3. Comprehensive Sections
- **Academic Programs (Filtered by Level)**:
  - B.S. in Environmental Science (Ecology & Conservation Track)
  - B.S. in Climate & Water Systems (Hydrology Track)
  - M.S. in Environmental Dynamics
  - Ph.D. in Global Earth Systems (Fully Funded)
  - Minor in Sustainable Resource Management
  - Professional Certificate in Environmental GIS & Remote Sensing
  - Interactive curriculum modal with course pathways and career outcomes.
- **Administration & Faculty Directory**:
  - Filterable by *Chairs & Directors*, *Advising & Student Services*, and *Lab & Operations*.
  - Direct contact options, office numbers, and email links.
- **Related Events & Calendar**:
  - Upcoming seminars, river basin fieldwork trips, and drone photogrammetry workshops.
  - Category filters and RSVP modal.
- **Student Portal SSO Experience**:
  - Mock single sign-on login system for students.
  - Post-login student dashboard preview with course registration, lab safety badges, and field research permits.

---

## 🚀 How to Run Locally

You can open `index.html` directly in any web browser, or launch a lightweight local HTTP server using Python:

```bash
cd /home/yourname/.gemini/antigravity/scratch/environmental-science-dept
python3 -m http.server 8000
```

Then visit [http://localhost:8000](http://localhost:8000) in your browser.

---

## 📁 File Structure & Downloads

```
environmental-science-dept/
├── environmental-science-dept.zip # Complete downloadable source code archive
├── index.html                     # Main HTML5 webpage containing all semantic sections and Tailwind styling
├── app.js                         # Interactive logic (filtering, modal management, campus map toggling, SSO simulation)
└── README.md                      # Documentation and project overview
```

### 📦 Downloadable Source Code
The full source bundle is packaged and ready for distribution:
- **Direct file path**: [`environmental-science-dept.zip`](file:///home/yourname/.gemini/antigravity/scratch/environmental-science-dept/environmental-science-dept.zip)
- **In-browser download**: A **"Download Source"** button is integrated directly into the website's navigation bar, hero banner, mobile menu, and footer.
