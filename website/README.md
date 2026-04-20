# BGC-QDR Website

## 🎨 Palantir-Style Website with Full Backend Integration

A modern, interactive website showcasing the BGC-QDR quantum machine learning pipeline for biosynthetic gene cluster discovery.

## ✅ What's Included

- **Frontend** (Vite + Vanilla JS)
  - ✅ Video background (DNA helix)
  - ✅ Smooth scroll animations
  - ✅ Interactive demo section
  - ✅ Real-time pipeline execution
  - ✅ File upload (drag & drop)
  
- **Backend** (Flask API)
  - ✅ RESTful API endpoints
  - ✅ Pipeline integration
  - ✅ File processing
  - ✅ Results download

## 🚀 Quick Start

### Option 1: Automated Startup (Recommended)

```powershell
# Windows PowerShell
.\start_website.ps1
```

This will:
1. Install all dependencies
2. Start Flask backend (port 5000)
3. Start Vite frontend (port 3000)
4. Open browser automatically

### Option 2: Manual Startup

**Terminal 1 - Backend:**
```bash
pip install -r backend_requirements.txt
python backend_api.py
```

**Terminal 2 - Frontend:**
```bash
cd website
npm install
npm run dev
```

## 🌐 Access

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:5000/api
- **Health Check**: http://localhost:5000/api/health

## 📁 Project Structure

```
.
├── website/
│   ├── index.html          ✅ Complete HTML with all sections
│   ├── style.css           ✅ Palantir-inspired styling
│   ├── script.js           ✅ Backend integration + animations
│   ├── package.json        ✅ Vite config
│   └── vite.config.js      ✅ Dev server config
│
├── backend_api.py          ✅ Flask REST API
├── backend_requirements.txt ✅ Python dependencies
├── start_website.ps1       ✅ Automated startup script
└── README.md               ✅ This file
```

## 🎯 Features

### Hero Section
- **Video Background** - DNA helix animation (like Palantir.com)
- **Smooth Scroll** - Animated scroll indicator
- **Call-to-Action** - Interactive buttons

### Pipeline Visualization
- **4 Product Rows** - Each phase with descriptions
- **Hover Effects** - Scale and translate animations
- **Scroll Reveal** - Staggered entrance animations

### Interactive Demo
- **File Upload** - Drag & drop FASTA files
- **Sample Data** - One-click demo with sample genome
- **Real-time Progress** - Live pipeline execution
- **Results Display** - Top drug candidates with scores
- **Download** - Export full results as JSON

### Stats Bar
- **Count-up Animation** - Numbers animate on scroll
- **Live Data** - Fetches real stats from backend

### Results Section
- **Benchmark Cards** - VQC, novelty, validation metrics
- **Fade-up Animations** - Smooth entrance effects

## 🔌 Backend API Endpoints

### GET /api/health
Health check
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "pipeline": "BGC-QDR"
}
```

### GET /api/stats
Get pipeline statistics
```json
{
  "total_bgcs": 68,
  "virtual_bgcs": 14,
  "vqc_accuracy": 0.804,
  "mibig_size": 2636
}
```

### POST /api/detect
Phase 1-2: BGC Detection
```bash
curl -X POST http://localhost:5000/api/detect \
  -F "fasta_file=@sample.fasta"
```

### POST /api/reconstruct
Phase 3: Graph Reconstruction
```bash
curl -X POST http://localhost:5000/api/reconstruct \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job_1234567890"}'
```

### POST /api/novelty
Phase 4-5: Novelty Assessment
```bash
curl -X POST http://localhost:5000/api/novelty \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job_1234567890"}'
```

### POST /api/rank
Phase 6: VQC Ranking
```bash
curl -X POST http://localhost:5000/api/rank \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job_1234567890"}'
```

### GET /api/results/{job_id}
Download complete results
```bash
curl -O http://localhost:5000/api/results/job_1234567890
```

## 🎨 Design System

### Colors
```css
--ink:    #0a0a0a  (text)
--paper:  #f4f3ef  (background)
--muted:  #888     (secondary text)
--rule:   rgba(0,0,0,0.09)  (borders)
```

### Typography
- **Serif**: DM Serif Display (headlines)
- **Sans**: DM Sans (body)
- **Mono**: DM Mono (labels, code)

### Video Background
- **Source**: Mixkit DNA helix video
- **Fallback**: Gradient overlay
- **Performance**: Optimized for all devices

## 🔧 Customization

### Change Backend URL
Edit `website/script.js`:
```javascript
const API_BASE_URL = 'http://your-server.com/api';
```

### Update Video Background
Edit `website/index.html`:
```html
<source src="your-video-url.mp4" type="video/mp4">
```

### Modify Pipeline Phases
Edit sections in `website/index.html` with class `.product-row`

## 📱 Responsive Design

- **Desktop**: Full 3-column layout
- **Tablet**: 2-column grid
- **Mobile**: Single column stack

Breakpoint: `@media (max-width: 900px)`

## 🌐 Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## 📦 Dependencies

### Frontend
- **Vite 5.0**: Dev server + HMR
- **No frameworks**: Pure vanilla JS

### Backend
- **Flask 3.0**: Web framework
- **flask-cors 4.0**: CORS support

## 🐛 Troubleshooting

### Backend not starting
```bash
# Check if port 5000 is available
netstat -ano | findstr :5000

# Install dependencies
pip install -r backend_requirements.txt
```

### Frontend not loading
```bash
# Clear node_modules and reinstall
cd website
rm -rf node_modules
npm install
npm run dev
```

### Video not playing
- Check internet connection (video is from CDN)
- Try different browser
- Check browser console for errors

### CORS errors
- Make sure backend is running on port 5000
- Check `flask-cors` is installed
- Verify `API_BASE_URL` in script.js

## 🚀 Deployment

### Frontend (Netlify/Vercel)
```bash
cd website
npm run build
# Deploy dist/ folder
```

### Backend (Heroku/Railway)
```bash
# Create Procfile
echo "web: python backend_api.py" > Procfile

# Deploy
git push heroku main
```

### Environment Variables
```bash
# Frontend
VITE_API_URL=https://your-backend.com/api

# Backend
FLASK_ENV=production
PORT=5000
```

## 📚 Resources

- [Vite Docs](https://vitejs.dev/)
- [Flask Docs](https://flask.palletsprojects.com/)
- [Palantir Design](https://www.palantir.com/)
- [BGC-QDR Paper](../BGC-QDR-Paper-v3.docx)

## 🎓 Credits

- **Design Inspiration**: Palantir.com
- **Video**: Mixkit (free stock footage)
- **Fonts**: DM Serif Display, DM Sans, DM Mono
- **Framework**: Vite + Flask

## 📄 License

Same as BGC-QDR project license.

---

**Status**: ✅ Complete and ready to use!

**Next**: Run `.\start_website.ps1` to launch! 🚀
