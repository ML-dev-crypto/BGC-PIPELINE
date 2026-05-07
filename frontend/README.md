# Frontend Setup Instructions

## Quick Setup

1. **Copy the index.html from "New folder":**
   ```bash
   # Windows PowerShell
   Copy-Item "../New folder/index.html" "index.html"
   
   # Or manually copy the file
   ```

2. **Add the JavaScript and CSS links to index.html:**
   
   Add these lines in the `<head>` section, right before the closing `</head>` tag:
   ```html
   <link rel="stylesheet" href="styles.css">
   ```
   
   Add this line at the end of the `<body>` section, right before the closing `</body>` tag:
   ```html
   <script src="app.js"></script>
   ```

3. **Copy the video file:**
   ```bash
   # Windows PowerShell
   Copy-Item "../New folder/DNA.mp4" "assets/DNA.mp4"
   ```

4. **Update the video source in index.html:**
   
   Find this line:
   ```html
   <source src="dna.mp4" type="video/mp4">
   ```
   
   Change it to:
   ```html
   <source src="assets/DNA.mp4" type="video/mp4">
   ```

## File Structure

```
frontend/
├── index.html          # Main HTML (copy from New folder)
├── app.js             # JavaScript with API integration (already created)
├── styles.css         # Additional styles (already created)
└── assets/
    └── DNA.mp4        # Background video (copy from New folder)
```

## Testing

1. Start the backend server:
   ```bash
   cd ..
   python backend_api.py
   ```

2. Start the frontend server:
   ```bash
   python -m http.server 3000
   ```

3. Open http://localhost:3000 in your browser

## Integration Points

The frontend connects to the backend through these key functions:

- `fetchStats()` - Loads pipeline statistics
- `runDetection()` - Starts BGC detection
- `runCompletePipeline()` - Runs all 6 phases
- `showUploadModal()` - Opens file upload interface
- `displayResults()` - Shows analysis results

All functions are available globally through `window.BGC.*`

## Customization

### Change API URL

Edit `app.js`:
```javascript
const API_BASE_URL = 'http://your-server:5000/api';
```

### Modify Colors

Edit the CSS variables in `index.html`:
```css
:root {
  --paper:  #f4f3ef;
  --ink:    #0a0a0a;
  --teal:   #2bc8b7;
  /* ... */
}
```

### Add New Features

1. Add HTML structure in `index.html`
2. Add styles in `styles.css`
3. Add functionality in `app.js`

## Troubleshooting

**Video not playing:**
- Check that `assets/DNA.mp4` exists
- Verify the video path in index.html
- Try a different browser

**API calls failing:**
- Verify backend is running on port 5000
- Check browser console (F12) for errors
- Verify CORS is enabled in backend

**Styles not loading:**
- Check that `styles.css` is linked in index.html
- Clear browser cache (Ctrl+F5)
- Check browser console for 404 errors

**JavaScript not working:**
- Check that `app.js` is linked in index.html
- Open browser console (F12) to see errors
- Verify API_BASE_URL is correct
