# NEXUS BGC - Full-Stack Application

A complete full-stack web application for BGC (Biosynthetic Gene Cluster) detection and analysis from environmental DNA samples.

## 🎯 Overview

**NEXUS BGC** combines a beautiful Palantir-style frontend with a powerful Python-based BGC analysis pipeline to create an end-to-end solution for:

- eDNA sample analysis
- BGC detection and classification
- Graph-based reconstruction
- Novelty assessment
- VQC (Virtual Quality Control) ranking
- Forensic-grade reporting

## 🏗️ Architecture

```
┌─────────────────────────────────────┐
│   Frontend (Port 3000)              │
│   - Palantir-style UI               │
│   - DNA video background            │
│   - Interactive pipeline viz        │
│   - Real-time stats                 │
└──────────────┬──────────────────────┘
               │ REST API
┌──────────────▼──────────────────────┐
│   Backend API (Port 5000)           │
│   - Flask REST API                  │
│   - CORS enabled                    │
│   - File upload handling            │
│   - Job management                  │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   BGC-QDR Pipeline                  │
│   - ORF prediction (Prodigal)       │
│   - BGC classification              │
│   - Graph reconstruction            │
│   - Novelty assessment              │
│   - VQC ranking                     │
└─────────────────────────────────────┘
```

## 📁 Project Structure

```
web.dv/
├── frontend/                    # Frontend application
│   ├── index.html              # Main HTML (copy from New folder)
│   ├── app.js                  # JavaScript with API integration
│   ├── styles.css              # Additional styles for modals
│   └── assets/
│       └── DNA.mp4             # Background video
│
├── backend_api.py              # Flask REST API server
├── backend_requirements.txt    # Python dependencies
│
├── call_orfs.py               # ORF calling with Prodigal
├── classify_bgcs.py           # BGC classification engine
├── benchmark_bgcqdr.py        # Performance benchmarking
├── compare_with_deepbgc.py    # Comparison with DeepBGC
│
├── uploads/                   # User-uploaded FASTA files
├── results/                   # Pipeline results (JSON)
├── edna_fasta/               # Sample eDNA datasets
├── benchmark_results/        # Benchmark data
│
├── start_fullstack.ps1       # Startup script (Windows)
├── FULLSTACK_README.md       # This file
└── FULLSTACK_INTEGRATION.md  # Detailed integration guide
```

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** with pip
- **Modern web browser** (Chrome, Firefox, Edge, Safari)
- **Prodigal** (optional, for ORF prediction)

### Installation

1. **Install Python dependencies:**
   ```bash
   pip install -r backend_requirements.txt
   ```

2. **Copy frontend files:**
   ```bash
   # Copy the index.html from New folder to frontend/
   cp "New folder/index.html" frontend/index.html
   
   # Copy the video file
   cp "New folder/DNA.mp4" frontend/assets/DNA.mp4
   ```

3. **Create necessary directories:**
   ```bash
   mkdir -p uploads results frontend/assets
   ```

### Running the Application

#### Option 1: Automated Startup (Windows)
```powershell
.\start_fullstack.ps1
```

This script will:
- Check Python installation
- Install missing dependencies
- Create necessary directories
- Copy video assets
- Start backend server (port 5000)
- Start frontend server (port 3000)
- Monitor both processes

#### Option 2: Manual Startup

**Terminal 1 - Backend:**
```bash
python backend_api.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
python -m http.server 3000
```

### Access the Application

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:5000/api
- **API Health:** http://localhost:5000/api/health

## 🎨 Features

### Frontend Features

1. **Hero Section**
   - Animated DNA video background
   - Text scramble effect on headline
   - "Analyse a Sample" CTA button
   - Smooth scroll animations

2. **Pipeline Visualization**
   - 4 interactive pipeline phases
   - Hover effects with expansion
   - SVG illustrations for each phase
   - Click to view phase details

3. **Stats Dashboard**
   - Real-time statistics from API
   - Animated counter effects
   - BGC detection metrics
   - VQC accuracy display

4. **Sample Upload**
   - Drag-and-drop file upload
   - Support for .fasta, .fa, .fna files
   - Sample data option
   - File size validation

5. **Results Display**
   - Interactive results modal
   - BGC candidate table
   - Confidence score visualization
   - Download complete results

### Backend Features

1. **REST API Endpoints**
   - `GET /api/health` - Health check
   - `GET /api/stats` - Pipeline statistics
   - `POST /api/detect` - BGC detection
   - `POST /api/reconstruct` - Graph reconstruction
   - `POST /api/novelty` - Novelty assessment
   - `POST /api/rank` - VQC ranking
   - `GET /api/results/<job_id>` - Download results

2. **File Management**
   - Secure file upload handling
   - Job-based result storage
   - Automatic cleanup
   - Sample data support

3. **Pipeline Integration**
   - Prodigal ORF prediction
   - BGC classification rules
   - Graph-based reconstruction
   - Novelty scoring
   - VQC ranking algorithm

## 📊 API Usage Examples

### Health Check
```bash
curl http://localhost:5000/api/health
```

### Get Statistics
```bash
curl http://localhost:5000/api/stats
```

### Run Detection with Sample Data
```bash
curl -X POST http://localhost:5000/api/detect \
  -F "use_sample=true"
```

### Run Detection with File Upload
```bash
curl -X POST http://localhost:5000/api/detect \
  -F "fasta_file=@sample.fasta"
```

### Run Complete Pipeline
```javascript
// Using the frontend JavaScript API
await window.BGC.runCompletePipeline(null, true); // Use sample data
```

## 🔧 Configuration

### Backend Configuration

Edit `backend_api.py`:

```python
# Port configuration
app.run(debug=True, host='0.0.0.0', port=5000)

# Upload folder
UPLOAD_FOLDER = Path('uploads')

# Results folder
RESULTS_FOLDER = Path('results')

# Sample data path
SAMPLE_FASTA = Path('edna_fasta/GCA_000205625.1.fasta')
```

### Frontend Configuration

Edit `frontend/app.js`:

```javascript
// API base URL
const API_BASE_URL = 'http://localhost:5000/api';

// File size limit (bytes)
const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB
```

## 🧪 Testing

### Test Backend API
```bash
# Health check
curl http://localhost:5000/api/health

# Get stats
curl http://localhost:5000/api/stats

# Run detection
curl -X POST http://localhost:5000/api/detect -F "use_sample=true"
```

### Test Frontend
1. Open http://localhost:3000
2. Click "Analyse a Sample"
3. Choose "Use Sample Data"
4. Watch the pipeline execute
5. View results

## 📦 Deployment

### Development
- Use the provided startup scripts
- Flask debug mode enabled
- CORS allows all origins

### Production

1. **Disable Flask debug mode:**
   ```python
   app.run(debug=False, host='0.0.0.0', port=5000)
   ```

2. **Use production WSGI server:**
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 backend_api:app
   ```

3. **Serve frontend with Nginx:**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           root /path/to/frontend;
           try_files $uri $uri/ /index.html;
       }
       
       location /api {
           proxy_pass http://localhost:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

4. **Use Docker (Recommended):**
   ```bash
   # Already have docker-compose.yml in project
   docker-compose up -d
   ```

## 🐛 Troubleshooting

### Backend won't start
- Check Python version: `python --version`
- Install dependencies: `pip install -r backend_requirements.txt`
- Check port 5000 is available: `netstat -an | findstr 5000`

### Frontend can't connect to backend
- Verify backend is running: `curl http://localhost:5000/api/health`
- Check CORS configuration in `backend_api.py`
- Check browser console for errors (F12)

### File upload fails
- Check file size (max 100MB)
- Verify file format (.fasta, .fa, .fna)
- Check `uploads/` directory exists and is writable

### Video not playing
- Verify `DNA.mp4` exists in `frontend/assets/`
- Check browser console for errors
- Try different browser

## 📝 Development

### Adding New API Endpoints

1. Add route in `backend_api.py`:
   ```python
   @app.route('/api/my-endpoint', methods=['POST'])
   def my_endpoint():
       # Your logic here
       return jsonify({'result': 'success'})
   ```

2. Add function in `frontend/app.js`:
   ```javascript
   async function callMyEndpoint(data) {
       const response = await fetch(`${API_BASE_URL}/my-endpoint`, {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify(data)
       });
       return await response.json();
   }
   ```

### Customizing the UI

- Edit `frontend/index.html` for structure
- Edit inline `<style>` in index.html for main styles
- Edit `frontend/styles.css` for modal/component styles
- Edit `frontend/app.js` for functionality

## 📚 Documentation

- **API Documentation:** See `FULLSTACK_INTEGRATION.md`
- **Pipeline Details:** See `CURRENT_STATUS.md`
- **Docker Setup:** See `DOCKER_SETUP_COMPLETE.md`
- **Benchmarks:** See `benchmark_results/benchmark_report.txt`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is part of the BGC-QDR pipeline research.

## 🙏 Acknowledgments

- **Frontend Design:** Inspired by Palantir's design system
- **Fonts:** DM Sans, DM Serif Display, DM Mono (Google Fonts)
- **Icons:** Custom SVG illustrations
- **Pipeline:** BGC-QDR research project

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review the integration guide
3. Check browser console for errors
4. Verify backend logs

---

**Version:** 1.0.0  
**Last Updated:** 2026-05-07  
**Status:** ✅ Ready for use

**Quick Links:**
- Frontend: http://localhost:3000
- Backend: http://localhost:5000/api
- Health Check: http://localhost:5000/api/health
