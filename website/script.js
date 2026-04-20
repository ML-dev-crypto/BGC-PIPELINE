/* ══════════════════════════════════════════════════════════════
   BGC-QDR Website - Animations + Backend Integration
   ══════════════════════════════════════════════════════════════ */

// Backend API Configuration
const API_BASE_URL = 'http://localhost:5000/api';  // Change to your backend URL

// Video Background Handler
const heroVideo = document.getElementById('heroVideo');
if (heroVideo) {
  heroVideo.addEventListener('loadeddata', () => {
    console.log('✅ Video background loaded successfully');
    heroVideo.style.opacity = '0.6';
  });
  
  heroVideo.addEventListener('error', (e) => {
    console.log('⚠️ Video failed to load, using animated background fallback');
    heroVideo.style.display = 'none';
  });
  
  // Force play (some browsers need this)
  heroVideo.play().catch(err => {
    console.log('Video autoplay prevented, using animated background');
  });
}

// 1. NAV SCROLL
const nav = document.getElementById('nav');
if (nav) {
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 80);
  }, { passive: true });
}

// 2. COUNT-UP ANIMATION
function countUp(el, target, suffix, dur) {
  let start = null;
  function step(ts) {
    if (!start) start = ts;
    const p = Math.min((ts - start) / dur, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(ease * target) + suffix;
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

const statsBar = document.getElementById('stats-bar');
if (statsBar) {
  let statsDone = false;
  const statsObs = new IntersectionObserver(entries => {
    if (entries[0].isIntersecting && !statsDone) {
      statsDone = true;
      document.querySelectorAll('.stat-num').forEach(el => {
        countUp(el, +el.dataset.count, el.dataset.suffix, 1800);
      });
    }
  }, { threshold: 0.4 });
  statsObs.observe(statsBar);
}

// 3. SCROLL REVEAL (product rows + fade-up)
const revealObs = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      const delay = +(e.target.dataset.delay || 0);
      setTimeout(() => e.target.classList.add('visible'), delay);
      revealObs.unobserve(e.target);
    }
  });
}, { threshold: 0.15 });

document.querySelectorAll('.product-row, .fade-up, .result-card').forEach(el => {
  revealObs.observe(el);
});

// 4. FILE UPLOAD HANDLING
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const runAnalysisBtn = document.getElementById('runAnalysis');
const useSampleBtn = document.getElementById('useSample');
const demoResults = document.getElementById('demoResults');
const progressFill = document.getElementById('progressFill');
const resultsOutput = document.getElementById('resultsOutput');

let selectedFile = null;

// Click to upload
if (uploadArea && fileInput) {
  uploadArea.addEventListener('click', () => fileInput.click());
  
  // File selection
  fileInput.addEventListener('change', (e) => {
    selectedFile = e.target.files[0];
    if (selectedFile) {
      uploadArea.querySelector('p').textContent = `Selected: ${selectedFile.name}`;
      uploadArea.style.borderColor = 'rgba(59, 130, 246, 0.5)';
    }
  });
  
  // Drag and drop
  uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = 'rgba(59, 130, 246, 0.5)';
  });
  
  uploadArea.addEventListener('dragleave', () => {
    uploadArea.style.borderColor = 'rgba(255,255,255,0.2)';
  });
  
  uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    selectedFile = e.dataTransfer.files[0];
    if (selectedFile) {
      uploadArea.querySelector('p').textContent = `Selected: ${selectedFile.name}`;
      uploadArea.style.borderColor = 'rgba(59, 130, 246, 0.5)';
    }
  });
}

// 5. RUN ANALYSIS
if (runAnalysisBtn) {
  runAnalysisBtn.addEventListener('click', async () => {
    if (!selectedFile) {
      alert('Please select a FASTA file first');
      return;
    }
    
    await runPipelineAnalysis(selectedFile);
  });
}

// 6. USE SAMPLE DATA
if (useSampleBtn) {
  useSampleBtn.addEventListener('click', async () => {
    await runPipelineAnalysis(null, true);
  });
}

// 7. BACKEND API FUNCTIONS
async function runPipelineAnalysis(file, useSample = false) {
  try {
    // Show results section
    demoResults.style.display = 'block';
    resultsOutput.innerHTML = '<p>🔄 Initializing pipeline...</p>';
    progressFill.style.width = '10%';
    
    // Prepare form data
    const formData = new FormData();
    if (useSample) {
      formData.append('use_sample', 'true');
    } else if (file) {
      formData.append('fasta_file', file);
    }
    
    // Phase 1-2: Detection
    resultsOutput.innerHTML += '<p>🧬 Phase 1-2: CNN Detection + HMM Annotation...</p>';
    progressFill.style.width = '25%';
    
    const detectionResponse = await fetch(`${API_BASE_URL}/detect`, {
      method: 'POST',
      body: formData
    });
    
    if (!detectionResponse.ok) {
      throw new Error('Detection failed');
    }
    
    const detectionData = await detectionResponse.json();
    resultsOutput.innerHTML += `<p>✅ Detected ${detectionData.bgc_count} BGC regions</p>`;
    progressFill.style.width = '40%';
    
    // Phase 3: Reconstruction
    resultsOutput.innerHTML += '<p>🔗 Phase 3: Graph Reconstruction...</p>';
    const reconstructResponse = await fetch(`${API_BASE_URL}/reconstruct`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: detectionData.job_id })
    });
    
    const reconstructData = await reconstructResponse.json();
    resultsOutput.innerHTML += `<p>✅ Assembled ${reconstructData.virtual_bgc_count} virtual BGCs</p>`;
    progressFill.style.width = '60%';
    
    // Phase 4-5: Novelty
    resultsOutput.innerHTML += '<p>🔍 Phase 4-5: Novelty Assessment...</p>';
    const noveltyResponse = await fetch(`${API_BASE_URL}/novelty`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: detectionData.job_id })
    });
    
    const noveltyData = await noveltyResponse.json();
    resultsOutput.innerHTML += `<p>✅ ${noveltyData.novel_count} novel BGCs identified</p>`;
    progressFill.style.width = '80%';
    
    // Phase 6: VQC Ranking
    resultsOutput.innerHTML += '<p>⚛️ Phase 6: Quantum ML Ranking...</p>';
    const rankingResponse = await fetch(`${API_BASE_URL}/rank`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: detectionData.job_id })
    });
    
    const rankingData = await rankingResponse.json();
    progressFill.style.width = '100%';
    
    // Display final results
    resultsOutput.innerHTML += '<p style="margin-top:20px;"><strong>🎯 Top Drug Candidates:</strong></p>';
    rankingData.top_candidates.forEach((candidate, i) => {
      resultsOutput.innerHTML += `
        <p style="margin-left:20px;">
          ${i + 1}. ${candidate.bgc_id} - Score: ${candidate.score.toFixed(3)} 
          (${candidate.bgc_class})
        </p>
      `;
    });
    
    resultsOutput.innerHTML += `
      <p style="margin-top:20px;">
        <strong>📊 Summary:</strong><br>
        • BGC Regions: ${detectionData.bgc_count}<br>
        • Virtual BGCs: ${reconstructData.virtual_bgc_count}<br>
        • Novel BGCs: ${noveltyData.novel_count}<br>
        • VQC Accuracy: ${(rankingData.vqc_accuracy * 100).toFixed(1)}%
      </p>
    `;
    
    // Download results button
    resultsOutput.innerHTML += `
      <button class="btn-primary" style="margin-top:20px;" onclick="downloadResults('${detectionData.job_id}')">
        Download Full Report
      </button>
    `;
    
  } catch (error) {
    console.error('Pipeline error:', error);
    resultsOutput.innerHTML += `<p style="color:#ef4444;">❌ Error: ${error.message}</p>`;
    resultsOutput.innerHTML += '<p>Make sure the backend server is running on http://localhost:5000</p>';
  }
}

// 8. DOWNLOAD RESULTS
window.downloadResults = async function(jobId) {
  try {
    const response = await fetch(`${API_BASE_URL}/results/${jobId}`);
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bgc-qdr-results-${jobId}.json`;
    a.click();
  } catch (error) {
    console.error('Download error:', error);
    alert('Failed to download results');
  }
};

// 9. FETCH LIVE STATS (Optional - updates stats bar with real data)
async function fetchLiveStats() {
  try {
    const response = await fetch(`${API_BASE_URL}/stats`);
    const stats = await response.json();
    
    // Update stats bar with real data
    const statNums = document.querySelectorAll('.stat-num');
    if (statNums[0]) statNums[0].dataset.count = stats.total_bgcs;
    if (statNums[1]) statNums[1].dataset.count = stats.virtual_bgcs;
    if (statNums[2]) statNums[2].dataset.count = Math.round(stats.vqc_accuracy * 100);
    if (statNums[3]) statNums[3].dataset.count = stats.mibig_size;
  } catch (error) {
    console.log('Using default stats (backend not available)');
  }
}

// Fetch live stats on page load
fetchLiveStats();

console.log('🧬 BGC-QDR Website Loaded');
console.log('📊 Pipeline: 6 phases');
console.log('🔬 VQC: 6 qubits, 54 parameters');
console.log('🌐 Backend API:', API_BASE_URL);
