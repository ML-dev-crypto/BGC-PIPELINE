/**
 * NEXUS BGC Frontend - API Integration
 * Connects the Palantir-style UI to the BGC-QDR Pipeline Backend
 */

// Configuration
const API_BASE_URL = 'http://localhost:5000/api';

// State management
const state = {
  currentJobId: null,
  isProcessing: false,
  stats: null
};

// ============================================================================
// API CALLS
// ============================================================================

/**
 * Fetch pipeline statistics
 */
async function fetchStats() {
  try {
    const response = await fetch(`${API_BASE_URL}/stats`);
    if (!response.ok) throw new Error('Failed to fetch stats');
    const data = await response.json();
    state.stats = data;
    updateStatsDisplay(data);
    return data;
  } catch (error) {
    console.error('Error fetching stats:', error);
    showNotification('Failed to load statistics', 'error');
  }
}

/**
 * Run BGC detection (Phase 1-2)
 */
async function runDetection(file = null, useSample = false, excludeSynthetic = false) {
  try {
    state.isProcessing = true;
    showLoadingState('Detecting BGCs...');
    
    const formData = new FormData();
    if (file) {
      formData.append('fasta_file', file);
    }
    formData.append('use_sample', useSample ? 'true' : 'false');
    formData.append('exclude_synthetic', excludeSynthetic ? 'true' : 'false');
    
    const response = await fetch(`${API_BASE_URL}/detect`, {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) throw new Error('Detection failed');
    const data = await response.json();
    
    state.currentJobId = data.job_id;
    
    // Show notification with QC info
    let message = `Detection complete! Found ${data.bgc_count} BGCs`;
    if (data.qc_summary && data.qc_summary.synthetic_excluded > 0) {
      message += ` (${data.qc_summary.synthetic_excluded} synthetic excluded)`;
    }
    showNotification(message, 'success');
    
    return data;
  } catch (error) {
    console.error('Error in detection:', error);
    showNotification('BGC detection failed', 'error');
    throw error;
  } finally {
    state.isProcessing = false;
    hideLoadingState();
  }
}

/**
 * Run graph reconstruction (Phase 3)
 */
async function runReconstruction(jobId) {
  try {
    showLoadingState('Reconstructing BGC graphs...');
    
    const response = await fetch(`${API_BASE_URL}/reconstruct`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId })
    });
    
    if (!response.ok) throw new Error('Reconstruction failed');
    const data = await response.json();
    
    showNotification(`Reconstruction complete! ${data.virtual_bgc_count} virtual BGCs`, 'success');
    return data;
  } catch (error) {
    console.error('Error in reconstruction:', error);
    showNotification('Graph reconstruction failed', 'error');
    throw error;
  } finally {
    hideLoadingState();
  }
}

/**
 * Run novelty assessment (Phase 4-5)
 */
async function runNoveltyAssessment(jobId) {
  try {
    showLoadingState('Assessing novelty...');
    
    const response = await fetch(`${API_BASE_URL}/novelty`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId })
    });
    
    if (!response.ok) throw new Error('Novelty assessment failed');
    const data = await response.json();
    
    showNotification(`Novelty assessment complete! ${data.novel_count}/${data.total_count} novel BGCs`, 'success');
    return data;
  } catch (error) {
    console.error('Error in novelty assessment:', error);
    showNotification('Novelty assessment failed', 'error');
    throw error;
  } finally {
    hideLoadingState();
  }
}

/**
 * Run VQC ranking (Phase 6)
 */
async function runRanking(jobId) {
  try {
    showLoadingState('Ranking BGC candidates...');
    
    const response = await fetch(`${API_BASE_URL}/rank`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId })
    });
    
    if (!response.ok) throw new Error('Ranking failed');
    const data = await response.json();
    
    showNotification(`Ranking complete! VQC accuracy: ${(data.vqc_accuracy * 100).toFixed(1)}%`, 'success');
    displayResults(data);
    return data;
  } catch (error) {
    console.error('Error in ranking:', error);
    showNotification('VQC ranking failed', 'error');
    throw error;
  } finally {
    hideLoadingState();
  }
}

/**
 * Run complete pipeline
 */
async function runCompletePipeline(file = null, useSample = false, excludeSynthetic = false) {
  try {
    // Phase 1-2: Detection
    const detectionResult = await runDetection(file, useSample, excludeSynthetic);
    const jobId = detectionResult.job_id;
    
    // Phase 3: Reconstruction
    await runReconstruction(jobId);
    
    // Phase 4-5: Novelty
    await runNoveltyAssessment(jobId);
    
    // Phase 6: Ranking
    const rankingResult = await runRanking(jobId);
    
    showNotification('Pipeline complete! 🎉', 'success');
    return rankingResult;
    
  } catch (error) {
    console.error('Pipeline error:', error);
    showNotification('Pipeline failed. Please try again.', 'error');
  }
}

/**
 * Download results
 */
async function downloadResults(jobId) {
  try {
    const response = await fetch(`${API_BASE_URL}/results/${jobId}`);
    if (!response.ok) throw new Error('Download failed');
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bgc_results_${jobId}.json`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    showNotification('Results downloaded successfully', 'success');
  } catch (error) {
    console.error('Error downloading results:', error);
    showNotification('Failed to download results', 'error');
  }
}

// ============================================================================
// UI UPDATES
// ============================================================================

/**
 * Update stats display with animated counters
 */
function updateStatsDisplay(stats) {
  // Update the stats section with real data
  const statElements = document.querySelectorAll('.stat-n');
  if (statElements.length >= 4) {
    statElements[0].dataset.c = stats.total_bgcs || 68;
    statElements[1].dataset.c = Math.round((stats.vqc_accuracy || 0.804) * 100);
    statElements[2].dataset.c = 24; // Active sites (static for now)
    statElements[3].dataset.c = 18; // Turnaround time (static)
  }
}

/**
 * Display results in a modal or results section
 */
function displayResults(data) {
  // Check for QC warnings
  const qcWarnings = [];
  if (data.sequence_qc && data.sequence_qc.overall_input_quality === 'poor') {
    qcWarnings.push({
      type: 'warning',
      message: `Input quality is poor (${data.sequence_qc.pass_rate}% pass rate). Results may be less reliable.`
    });
  }
  
  // Check for manual review flags
  const manualReviewCount = data.top_candidates.filter(c => c.requires_manual_review).length;
  if (manualReviewCount > 0) {
    qcWarnings.push({
      type: 'info',
      message: `${manualReviewCount} candidate(s) require manual review due to unknown classification.`
    });
  }
  
  // Build warnings HTML
  const warningsHTML = qcWarnings.length > 0 ? `
    <div class="qc-warnings">
      ${qcWarnings.map(w => `
        <div class="qc-warning qc-warning-${w.type}">
          <span class="warning-icon">${w.type === 'warning' ? '⚠️' : 'ℹ️'}</span>
          <span class="warning-text">${w.message}</span>
        </div>
      `).join('')}
    </div>
  ` : '';
  
  // Build score distribution sparkline
  const scoreDistHTML = data.score_distribution ? `
    <div class="score-distribution">
      <div class="dist-label">Score Distribution</div>
      <div class="dist-sparkline">
        ${data.score_distribution.histogram_bins.map(bin => `
          <div class="spark-bar" style="height: ${(bin.count / Math.max(...data.score_distribution.histogram_bins.map(b => b.count)) * 100)}%" 
               title="${bin.range}: ${bin.count} candidates"></div>
        `).join('')}
      </div>
      <div class="dist-stats">
        <span>Min: ${data.score_distribution.min}</span>
        <span>Mean: ${data.score_distribution.mean}</span>
        <span>Max: ${data.score_distribution.max}</span>
      </div>
    </div>
  ` : '';
  
  const resultsHTML = `
    <div class="results-modal" id="resultsModal">
      <div class="results-content">
        <div class="results-header">
          <h2>BGC Analysis Results</h2>
          <button class="close-btn" onclick="closeResults()">×</button>
        </div>
        
        ${warningsHTML}
        
        <div class="results-summary">
          <div class="summary-card">
            <div class="summary-label">Job ID</div>
            <div class="summary-value">${data.job_id}</div>
            ${data.input_hash ? `<div class="summary-meta">Hash: ${data.input_hash}</div>` : ''}
          </div>
          <div class="summary-card">
            <div class="summary-label">VQC Accuracy</div>
            <div class="summary-value">${(data.vqc_accuracy * 100).toFixed(1)}%</div>
            ${scoreDistHTML}
          </div>
          <div class="summary-card">
            <div class="summary-label">Top Candidates</div>
            <div class="summary-value">${data.top_candidates.length}</div>
            <div class="summary-meta">${data.candidates_above_threshold} above threshold</div>
          </div>
          ${data.sequence_qc ? `
          <div class="summary-card">
            <div class="summary-label">Input Quality</div>
            <div class="summary-value quality-${data.sequence_qc.overall_input_quality || 'unknown'}">
              ${(data.sequence_qc.overall_input_quality || 'unknown').toUpperCase()}
            </div>
            <div class="summary-meta">${data.sequence_qc.passed_sequences}/${data.sequence_qc.total_sequences} passed QC</div>
          </div>
          ` : ''}
        </div>
        
        <div class="results-table">
          <h3>Top BGC Candidates</h3>
          <table>
            <thead>
              <tr>
                <th>BGC ID</th>
                <th>Class</th>
                <th>Score</th>
                <th>Percentile</th>
                <th>Novelty (%)</th>
                <th>Completeness</th>
              </tr>
            </thead>
            <tbody>
              ${data.top_candidates.map(candidate => `
                <tr class="${candidate.requires_manual_review ? 'requires-review' : ''}">
                  <td><code>${candidate.bgc_id}</code></td>
                  <td>
                    ${candidate.bgc_class}
                    ${candidate.requires_manual_review ? '<span class="review-badge">⚠️ Review</span>' : ''}
                  </td>
                  <td>
                    <div class="score-bar">
                      <div class="score-fill score-${candidate.confidence_level}" style="width: ${candidate.score * 100}%"></div>
                      <span class="score-text">${(candidate.score * 100).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td>${candidate.percentile_rank}%</td>
                  <td>${candidate.novelty.toFixed(2)}%</td>
                  <td>
                    <span class="completeness-badge completeness-${candidate.completeness >= 0.8 ? 'high' : candidate.completeness >= 0.5 ? 'medium' : 'low'}">
                      ${(candidate.completeness * 100).toFixed(0)}%
                    </span>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
        
        ${data.sequence_qc ? `
        <div class="qc-details">
          <h3>Sequence Quality Details</h3>
          <div class="qc-grid">
            <div class="qc-stat">
              <div class="qc-stat-label">Total Contigs</div>
              <div class="qc-stat-value">${data.sequence_qc.total_sequences}</div>
            </div>
            <div class="qc-stat">
              <div class="qc-stat-label">Passed QC</div>
              <div class="qc-stat-value">${data.sequence_qc.passed_sequences}</div>
            </div>
            <div class="qc-stat">
              <div class="qc-stat-label">Failed QC</div>
              <div class="qc-stat-value">${data.sequence_qc.failed_sequences}</div>
            </div>
            <div class="qc-stat">
              <div class="qc-stat-label">Pass Rate</div>
              <div class="qc-stat-value">${data.sequence_qc.pass_rate}%</div>
            </div>
          </div>
        </div>
        ` : ''}
        
        <div class="results-actions">
          <button class="btn-primary" onclick="downloadResults('${data.job_id}')">
            Download Complete Results
          </button>
          <button class="btn-secondary" onclick="runNewAnalysis()">
            Run New Analysis
          </button>
        </div>
        
        ${data.input_hash ? `
        <div class="results-footer">
          <small>Input Hash: <code>${data.input_hash}</code> | Processing Time: ${data.processing_time_seconds || 'N/A'}s ${data.cached ? '(cached)' : ''}</small>
        </div>
        ` : ''}
      </div>
    </div>
  `;
  
  // Remove existing modal if any
  const existingModal = document.getElementById('resultsModal');
  if (existingModal) existingModal.remove();
  
  // Add new modal
  document.body.insertAdjacentHTML('beforeend', resultsHTML);
}

/**
 * Show loading state
 */
function showLoadingState(message = 'Processing...') {
  const loadingHTML = `
    <div class="loading-overlay" id="loadingOverlay">
      <div class="loading-content">
        <div class="loading-spinner"></div>
        <div class="loading-message">${message}</div>
      </div>
    </div>
  `;
  
  const existing = document.getElementById('loadingOverlay');
  if (existing) {
    existing.querySelector('.loading-message').textContent = message;
  } else {
    document.body.insertAdjacentHTML('beforeend', loadingHTML);
  }
}

/**
 * Hide loading state
 */
function hideLoadingState() {
  const overlay = document.getElementById('loadingOverlay');
  if (overlay) overlay.remove();
}

/**
 * Show notification
 */
function showNotification(message, type = 'info') {
  const notificationHTML = `
    <div class="notification notification-${type}">
      ${message}
    </div>
  `;
  
  const notification = document.createElement('div');
  notification.innerHTML = notificationHTML;
  document.body.appendChild(notification.firstElementChild);
  
  setTimeout(() => {
    const el = document.querySelector('.notification');
    if (el) el.remove();
  }, 5000);
}

/**
 * Close results modal
 */
function closeResults() {
  const modal = document.getElementById('resultsModal');
  if (modal) modal.remove();
}

/**
 * Run new analysis
 */
function runNewAnalysis() {
  closeResults();
  showUploadModal();
}

/**
 * Show upload modal
 */
function showUploadModal() {
  const modalHTML = `
    <div class="upload-modal" id="uploadModal">
      <div class="upload-content">
        <div class="upload-header">
          <h2>Analyse eDNA Sample</h2>
          <button class="close-btn" onclick="closeUploadModal()">×</button>
        </div>
        
        <div class="upload-body">
          <div class="upload-option">
            <h3>Upload FASTA File</h3>
            <div class="file-drop-zone" id="dropZone">
              <input type="file" id="fastaFile" accept=".fasta,.fa,.fna" style="display:none">
              <div class="drop-zone-content">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                </svg>
                <p>Drop FASTA file here or click to browse</p>
                <span class="file-info">Supported: .fasta, .fa, .fna (max 100MB)</span>
              </div>
            </div>
            <div class="qc-options" style="margin-top: 15px;">
              <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="checkbox" id="excludeSynthetic" checked style="width: 18px; height: 18px; cursor: pointer;">
                <span style="font-size: 14px; color: #e0e0e0;">
                  Exclude synthetic/marker sequences (recommended for real analysis)
                </span>
              </label>
              <p style="font-size: 12px; color: #888; margin: 8px 0 0 26px;">
                Automatically detects and removes synthetic BGC markers to prevent inflated counts
              </p>
            </div>
            <button class="btn-primary" onclick="uploadAndAnalyse()">
              Upload & Analyse
            </button>
          </div>
          
          <div class="upload-divider">
            <span>OR</span>
          </div>
          
          <div class="upload-option">
            <h3>Use Sample Data</h3>
            <p>Try the pipeline with our sample eDNA dataset from environmental water samples.</p>
            <button class="btn-secondary" onclick="analyseSample()">
              Analyse Sample Data
            </button>
          </div>
        </div>
      </div>
    </div>
  `;
  
  document.body.insertAdjacentHTML('beforeend', modalHTML);
  
  // Setup file drop zone
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fastaFile');
  
  dropZone.addEventListener('click', () => fileInput.click());
  
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  
  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });
  
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      fileInput.files = files;
      updateFileInfo(files[0]);
    }
  });
  
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      updateFileInfo(e.target.files[0]);
    }
  });
}

/**
 * Close upload modal
 */
function closeUploadModal() {
  const modal = document.getElementById('uploadModal');
  if (modal) modal.remove();
}

/**
 * Update file info display
 */
function updateFileInfo(file) {
  const dropZone = document.getElementById('dropZone');
  const content = dropZone.querySelector('.drop-zone-content');
  content.innerHTML = `
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
      <polyline points="13 2 13 9 20 9"/>
    </svg>
    <p><strong>${file.name}</strong></p>
    <span class="file-info">${(file.size / 1024 / 1024).toFixed(2)} MB</span>
  `;
}

/**
 * Upload and analyse file
 */
async function uploadAndAnalyse() {
  const fileInput = document.getElementById('fastaFile');
  if (!fileInput.files.length) {
    showNotification('Please select a file first', 'error');
    return;
  }
  
  const file = fileInput.files[0];
  const excludeSynthetic = document.getElementById('excludeSynthetic')?.checked || false;
  closeUploadModal();
  await runCompletePipeline(file, false, excludeSynthetic);
}

/**
 * Analyse sample data
 */
async function analyseSample() {
  const excludeSynthetic = document.getElementById('excludeSynthetic')?.checked || false;
  closeUploadModal();
  await runCompletePipeline(null, true, excludeSynthetic);
}
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize the application
 */
function initApp() {
  console.log('🧬 NEXUS BGC Frontend initialized');
  
  // Fetch initial stats
  fetchStats();
  
  // Setup event listeners
  setupEventListeners();
  
  // Check API health
  checkAPIHealth();
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
  // "Analyse a Sample" button
  const analyseBtn = document.querySelector('.hbtn-cta');
  if (analyseBtn) {
    analyseBtn.addEventListener('click', (e) => {
      e.preventDefault();
      showUploadModal();
    });
  }
  
  // Pipeline rows - make them interactive
  const pipelineRows = document.querySelectorAll('.prow');
  pipelineRows.forEach((row, index) => {
    row.addEventListener('click', () => {
      showPhaseInfo(index + 1);
    });
  });
}

/**
 * Show phase information
 */
function showPhaseInfo(phase) {
  const phaseInfo = {
    1: {
      title: 'eDNA Extraction',
      description: 'Environmental DNA extraction from water samples using portable lysis kits.',
      details: 'Collect water and sediment at field sites. Extract microbial eDNA, concentrate and purify for sequencing.'
    },
    2: {
      title: 'BGC Sequencing',
      description: 'Shotgun metagenomic sequencing and BGC identification.',
      details: 'Assemble reads and identify biosynthetic gene clusters using AntiSMASH and BiG-SCAPE algorithms.'
    },
    3: {
      title: 'AI Drug Profiling',
      description: 'AI-powered matching against drug biosynthetic pathways.',
      details: 'Match detected BGC signatures against 3,400+ drug and precursor biosynthetic pathways with confidence scoring.'
    },
    4: {
      title: 'Risk Mapping',
      description: 'Generate site-level risk scores and forensic reports.',
      details: 'Geolocate production hotspots and export forensic-grade reports for law enforcement and public health.'
    }
  };
  
  const info = phaseInfo[phase];
  if (info) {
    showNotification(`Phase ${phase}: ${info.title} - ${info.description}`, 'info');
  }
}

/**
 * Check API health
 */
async function checkAPIHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    if (!response.ok) throw new Error('API unhealthy');
    const data = await response.json();
    console.log('✅ API Health:', data);
  } catch (error) {
    console.error('❌ API Health Check Failed:', error);
    showNotification('Backend API is not responding. Please start the server.', 'error');
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

// Export functions for global access
window.BGC = {
  runDetection,
  runReconstruction,
  runNoveltyAssessment,
  runRanking,
  runCompletePipeline,
  downloadResults,
  fetchStats,
  showUploadModal,
  closeUploadModal,
  closeResults,
  runNewAnalysis,
  uploadAndAnalyse,
  analyseSample
};
