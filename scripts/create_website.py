#!/usr/bin/env python3
"""
Create BGC-QDR Website Files
"""
import os

# Create website directory
os.makedirs('website', exist_ok=True)

# HTML Content (simplified for now, will expand)
html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BGC-QDR - Quantum Biosynthetic Gene Cluster Discovery</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@300;400&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <nav class="nav" id="nav">
        <div class="nav-logo">
            <div class="nav-logo-main">BGC-QDR</div>
            <div class="nav-logo-sub">Quantum Drug Discovery Platform</div>
        </div>
        <ul class="nav-links">
            <li><a href="#pipeline">Pipeline</a></li>
            <li><a href="#results">Results</a></li>
            <li><a href="#paper">Research</a></li>
        </ul>
        <button class="nav-cta">Run Analysis</button>
    </nav>
    
    <section class="hero" id="hero">
        <canvas id="dna-canvas"></canvas>
        <div class="hero-content">
            <div class="hero-eyebrow">Environmental DNA · Quantum Machine Learning</div>
            <h1 class="hero-headline">
                Discover novel drug compounds<br>
                <em>from environmental DNA</em>
            </h1>
            <p class="hero-sub">
                A 6-phase quantum-classical hybrid pipeline that identifies biosynthetic 
                gene clusters from eDNA and ranks them by drug-discovery potential using 
                variational quantum circuits.
            </p>
            <div class="hero-actions">
                <button class="btn-primary">Analyze Sample</button>
                <button class="btn-ghost">View Pipeline →</button>
            </div>
        </div>
        <div class="scroll-cue">
            <div class="scroll-line"></div>
            <span>Scroll to explore</span>
        </div>
    </section>
    
    <div class="stats-bar" id="stats-bar">
        <div class="stat-cell">
            <div class="stat-num" data-count="68" data-suffix="">0</div>
            <div class="stat-label">BGC Regions Detected</div>
        </div>
        <div class="stat-cell">
            <div class="stat-num" data-count="14" data-suffix="">0</div>
            <div class="stat-label">Virtual BGCs Assembled</div>
        </div>
        <div class="stat-cell">
            <div class="stat-num" data-count="80" data-suffix="%">0%</div>
            <div class="stat-label">VQC Accuracy</div>
        </div>
        <div class="stat-cell">
            <div class="stat-num" data-count="2636" data-suffix="">0</div>
            <div class="stat-label">MiBIG Training Set</div>
        </div>
    </div>
    
    <footer>
        <span>BGC-QDR v1.0 · © 2026</span>
        <span>Built with Three.js + Vanilla JS</span>
    </footer>
    
    <script src="script.js"></script>
</body>
</html>"""

# Write HTML
with open('website/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("[OK] Created website/index.html")
print("📁 Website files ready in website/ directory")
print("\nNext steps:")
print("  1. Open website/index.html in a browser")
print("  2. Or run: python -m http.server 8000 --directory website")
print("  3. Then visit: http://localhost:8000")
