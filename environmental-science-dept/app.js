// Initialize Lucide Icons
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  setupActiveNavScroll();
});

// Mobile Menu Toggle
const mobileBtn = document.getElementById('mobile-menu-btn');
const mobileMenu = document.getElementById('mobile-menu');

if (mobileBtn && mobileMenu) {
  mobileBtn.addEventListener('click', () => {
    mobileMenu.classList.toggle('hidden');
  });
}

function closeMobileMenu() {
  if (mobileMenu) {
    mobileMenu.classList.add('hidden');
  }
}

// Campus Map Switcher (Campus View vs Floor Plan)
function switchMapView(view) {
  const campusDisplay = document.getElementById('campus-map-display');
  const floorDisplay = document.getElementById('floor-map-display');
  const btnCampus = document.getElementById('map-btn-campus');
  const btnFloor = document.getElementById('map-btn-floor');

  if (view === 'campus') {
    campusDisplay.classList.remove('hidden');
    floorDisplay.classList.add('hidden');

    btnCampus.className = 'px-3 py-1 rounded-lg font-bold bg-forest-800 text-white transition-all';
    btnFloor.className = 'px-3 py-1 rounded-lg font-bold text-slate-600 hover:text-slate-900 transition-all';
  } else {
    campusDisplay.classList.add('hidden');
    floorDisplay.classList.remove('hidden');

    btnCampus.className = 'px-3 py-1 rounded-lg font-bold text-slate-600 hover:text-slate-900 transition-all';
    btnFloor.className = 'px-3 py-1 rounded-lg font-bold bg-forest-800 text-white transition-all';
  }

  // Refresh icons
  if (window.lucide) lucide.createIcons();
}

// Staff / Administration Directory Filter
function filterStaff(category) {
  const cards = document.querySelectorAll('.staff-card');
  const buttons = document.querySelectorAll('.staff-tab-btn');

  buttons.forEach(btn => {
    if (btn.getAttribute('data-category') === category) {
      btn.className = 'staff-tab-btn active px-4 py-2 rounded-lg bg-forest-800 text-white transition-all';
    } else {
      btn.className = 'staff-tab-btn px-4 py-2 rounded-lg text-slate-600 hover:text-slate-900 transition-all';
    }
  });

  cards.forEach(card => {
    const cardCat = card.getAttribute('data-category');
    if (category === 'all' || cardCat === category) {
      card.style.display = 'flex';
    } else {
      card.style.display = 'none';
    }
  });
}

// Programs Filter
function filterPrograms(tier) {
  const cards = document.querySelectorAll('.program-card');
  const buttons = document.querySelectorAll('.program-tab-btn');

  buttons.forEach(btn => {
    if (btn.getAttribute('data-filter') === tier) {
      btn.className = 'program-tab-btn active px-4 py-2 rounded-lg bg-forest-800 text-white transition-all';
    } else {
      btn.className = 'program-tab-btn px-4 py-2 rounded-lg text-slate-600 hover:text-slate-900 transition-all';
    }
  });

  cards.forEach(card => {
    const cardTier = card.getAttribute('data-tier');
    if (tier === 'all' || cardTier === tier) {
      card.style.display = 'flex';
    } else {
      card.style.display = 'none';
    }
  });
}

// Events Filter
function filterEvents(category) {
  const cards = document.querySelectorAll('.event-card');
  const buttons = document.querySelectorAll('.event-filter-btn');

  buttons.forEach(btn => {
    if (btn.getAttribute('data-filter') === category) {
      btn.className = 'event-filter-btn active px-3.5 py-2 rounded-lg bg-forest-800 text-white transition-all';
    } else {
      btn.className = 'event-filter-btn px-3.5 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-all';
    }
  });

  cards.forEach(card => {
    const cardCat = card.getAttribute('data-category');
    if (category === 'all' || cardCat === category) {
      card.style.display = 'flex';
    } else {
      card.style.display = 'none';
    }
  });
}

// Student Portal Modal Handlers
function openPortalModal() {
  const modal = document.getElementById('portal-modal');
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closePortalModal() {
  const modal = document.getElementById('portal-modal');
  modal.classList.add('hidden');
  document.body.style.overflow = 'auto';
}

function handlePortalSubmit(e) {
  e.preventDefault();
  const form = document.getElementById('portal-form');
  const dashboard = document.getElementById('portal-mock-dashboard');
  
  // Simulate successful SSO handshake
  form.classList.add('hidden');
  dashboard.classList.remove('hidden');
  
  showToast("Single Sign-On Authenticated: Logged into Student Portal");
  if (window.lucide) lucide.createIcons();
}

// Program Details Modal Data & Handlers
const programDetailsMap = {
  'B.S. in Environmental Science (Ecology Track)': {
    degree: 'Bachelor of Science (B.S.) in Environmental Science',
    focus: 'Ecosystem Conservation & Terrestrial Ecology',
    duration: '4 Academic Years &bull; 120 Semester Credit Hours',
    description: 'This degree provides comprehensive foundational study in physical, biological, and earth systems with hands-on immersion in ecological sampling, population genetics, and landscape restoration.',
    curriculum: [
      'Year 1: Principles of Environmental Science, General Chemistry I & II, Calculus & Statistics',
      'Year 2: Soil Science & Biogeochemistry, Field Botany & Dendrology, Organic Chemistry',
      'Year 3: Wetland & Watershed Ecology, Ecological Restoration Lab, Remote Sensing in Conservation',
      'Year 4: Senior Environmental Capstone Project, Independent Field Thesis, Professional Internship'
    ],
    careers: ['Ecosystem Restoration Specialist', 'Wetland Delineator', 'State Department of Fish & Wildlife Biologist', 'Conservation Planner']
  },
  'B.S. in Climate & Water Systems': {
    degree: 'Bachelor of Science (B.S.) in Climate & Water Systems',
    focus: 'Atmospheric Physics, Hydrogeology, and Climate Risk',
    duration: '4 Academic Years &bull; 120 Semester Credit Hours',
    description: 'An analytical, mathematically rigorous pathway preparing graduates to address sea-level rise, watershed degradation, catastrophic drought, and municipal water security.',
    curriculum: [
      'Year 1: Atmospheric Dynamics, Earth Systems Geosciences, Differential Equations',
      'Year 2: Hydrogeology & Aquifer Dynamics, Applied Meteorology, Physics of Fluids',
      'Year 3: Spatial Climate Modeling, Water Quality Assessment & Toxicology, Coastal Dynamics',
      'Year 4: Climate Risk & Urban Infrastructure Capstone, Watershed Modeling Seminar'
    ],
    careers: ['Hydrological Modeler', 'Climate Risk Analyst for Financial/Insurance Firms', 'Water Resource Engineer', 'NOAA Scientific Specialist']
  },
  'M.S. in Environmental Dynamics': {
    degree: 'Master of Science (M.S.) in Environmental Dynamics',
    focus: 'Applied Analytical Methods & Interdisciplinary Research',
    duration: '2 Academic Years &bull; 36 Graduate Credit Hours',
    description: 'A research-intensive Master’s program emphasizing high-resolution mass spectrometry, advanced GIS spatial analytics, and direct publication in peer-reviewed journals.',
    curriculum: [
      'Advanced Biogeochemical Cycles & Trace Analysis',
      'Multivariate Environmental Statistics with R & Python',
      'Isotope Hydrology & Carbon Flux Measurement',
      'Graduate Research Thesis or Applied Practicum Project'
    ],
    careers: ['Senior Environmental Consultant', 'EPA Policy Specialist', 'Industrial Sustainability Officer', 'Path to Doctoral Programs']
  },
  'Ph.D. in Global Earth Systems': {
    degree: 'Doctor of Philosophy (Ph.D.) in Global Earth & Environmental Science',
    focus: 'Original Dissertation Research with Full Fellowship Funding',
    duration: '4 to 5 Academic Years &bull; Full Tuition + $34,000 Stipend',
    description: 'Prepares doctoral scholars for tenure-track academic appointments, national research laboratory leadership, and international climate summit delegations.',
    curriculum: [
      'Comprehensive Doctoral Qualifying Examination (Year 2)',
      'Dissertation Proposal Defense and Fellowship Grant Writing',
      'Field Station Research Expeditions & High-Performance Computing Modeling',
      'Final Dissertation Defense and Peer-Reviewed Publication'
    ],
    careers: ['University Professor', 'Senior Research Scientist (NASA / NOAA)', 'International Climate Policy Advisor', 'Lead Environmental Strategist']
  },
  'Minor in Sustainable Management': {
    degree: 'Undergraduate Minor in Sustainable Resource Management',
    focus: 'Interdisciplinary Policy, Economics, and Ecological Governance',
    duration: '18 Credit Hours &bull; Complementary to Any Major',
    description: 'Equips students majoring in Business, Political Science, Architecture, or Engineering with the foundational tools to drive sustainability within organizational frameworks.',
    curriculum: [
      'ENV 105: Human Ecology & Planetary Boundaries',
      'ENV 220: Environmental Law & Regulatory Compliance',
      'ENV 325: Circular Economy & Life Cycle Assessment',
      'ENV 410: Corporate Environmental, Social, and Governance (ESG) Strategies'
    ],
    careers: ['ESG Reporting Analyst', 'Urban Planning Associate', 'Environmental Compliance Officer', 'Non-Profit Project Coordinator']
  },
  'Certificate in Environmental GIS': {
    degree: 'Post-Baccalaureate / Undergraduate Professional Certificate in GIS',
    focus: 'Spatial Analysis, Satellite Remote Sensing, and Python Scripting',
    duration: '15 Credit Hours &bull; 2 Semesters',
    description: 'Designed to impart immediate industry-ready mastery of geospatial databases, satellite imagery classification, drone mapping, and spatial web app development.',
    curriculum: [
      'GIS 301: Fundamentals of Spatial Geographic Systems (ArcGIS Pro)',
      'GIS 350: Drone Photogrammetry & LiDAR Canopy Processing',
      'GIS 410: Python for Geospatial Automation & GDAL',
      'GIS 450: Web GIS & Interactive Map Dashboard Design'
    ],
    careers: ['GIS Analyst', 'Geospatial Intelligence Specialist', 'Drone Remote Sensing Technician', 'Conservation Cartographer']
  }
};

function openProgramModal(programKey) {
  const data = programDetailsMap[programKey];
  if (!data) return;

  const modal = document.getElementById('program-modal');
  const title = document.getElementById('program-modal-title');
  const content = document.getElementById('program-modal-content');

  title.innerText = data.degree;

  content.innerHTML = `
    <div class="bg-forest-50 p-4 rounded-2xl border border-forest-200 mb-4">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <span class="font-bold text-forest-900">${data.focus}</span>
        <span class="text-xs font-semibold text-forest-700 bg-white px-2.5 py-1 rounded-md border border-forest-300">${data.duration}</span>
      </div>
      <p class="mt-2 text-xs text-forest-800 leading-relaxed">${data.description}</p>
    </div>

    <div>
      <h4 class="font-bold text-slate-900 uppercase tracking-wider text-xs mb-2">Curriculum Pathway</h4>
      <ul class="space-y-1.5 list-disc list-inside text-slate-600">
        ${data.curriculum.map(item => `<li><span class="font-medium text-slate-800">${item}</span></li>`).join('')}
      </ul>
    </div>

    <div class="pt-4 border-t border-slate-100">
      <h4 class="font-bold text-slate-900 uppercase tracking-wider text-xs mb-2">Featured Career Outcomes</h4>
      <div class="flex flex-wrap gap-2">
        ${data.careers.map(career => `<span class="px-2.5 py-1 bg-slate-100 rounded-lg text-slate-700 font-semibold text-xs border border-slate-200">${career}</span>`).join('')}
      </div>
    </div>
  `;

  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeProgramModal() {
  const modal = document.getElementById('program-modal');
  modal.classList.add('hidden');
  document.body.style.overflow = 'auto';
}

// Contact / RSVP Modal Handlers
function openContactModal(context) {
  const modal = document.getElementById('contact-modal');
  const title = document.getElementById('contact-modal-title');
  const purposeInput = document.getElementById('contact-purpose');
  const alert = document.getElementById('contact-alert');

  alert.classList.add('hidden');
  title.innerText = `Contact: ${context || 'Department Office'}`;
  if (purposeInput) {
    purposeInput.value = context ? `Inquiry regarding: ${context}` : 'General Department Inquiry';
  }

  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeContactModal() {
  const modal = document.getElementById('contact-modal');
  modal.classList.add('hidden');
  document.body.style.overflow = 'auto';
}

function handleContactSubmit(e) {
  e.preventDefault();
  const alert = document.getElementById('contact-alert');
  const submitBtn = document.getElementById('contact-submit-btn');

  alert.classList.remove('hidden');
  submitBtn.disabled = true;
  submitBtn.innerText = "Submitted";

  showToast("Inquiry sent to Department Administration Desk");

  setTimeout(() => {
    closeContactModal();
    submitBtn.disabled = false;
    submitBtn.innerText = "Send Inquiry";
    alert.classList.add('hidden');
  }, 2000);
}

function rsvpEvent(eventName) {
  openContactModal(`RSVP for: ${eventName}`);
}

// Toast Notification Helper
function showToast(message) {
  const toast = document.getElementById('toast');
  const toastMessage = document.getElementById('toast-message');

  if (toast && toastMessage) {
    toastMessage.innerText = message;
    toast.classList.remove('translate-y-24', 'opacity-0');
    toast.classList.add('translate-y-0', 'opacity-100');

    setTimeout(() => {
      toast.classList.remove('translate-y-0', 'opacity-100');
      toast.classList.add('translate-y-24', 'opacity-0');
    }, 3500);
  }
}

// Active Nav link highlight on scroll
function setupActiveNavScroll() {
  const sections = document.querySelectorAll('section[id], main[id]');
  const navLinks = document.querySelectorAll('.nav-link');

  window.addEventListener('scroll', () => {
    let current = '';
    const scrollPos = window.pageYOffset + 120;

    sections.forEach(section => {
      const sectionTop = section.offsetTop;
      const sectionHeight = section.clientHeight;
      if (scrollPos >= sectionTop && scrollPos < sectionTop + sectionHeight) {
        current = section.getAttribute('id');
      }
    });

    navLinks.forEach(link => {
      link.classList.remove('text-forest-900', 'bg-forest-100/80', 'font-bold');
      if (link.getAttribute('href') === `#${current}`) {
        link.classList.add('text-forest-900', 'bg-forest-100/80', 'font-bold');
      }
    });
  });
}
