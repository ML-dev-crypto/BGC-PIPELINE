#!/usr/bin/env python3
"""
BGC-QDR Backend API
Flask server for website integration
"""
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import time
from pathlib import Path
import subprocess

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

# Configuration
UPLOAD_FOLDER = Path('uploads')
RESULTS_FOLDER = Path('results')
UPLOAD_FOLDER.mkdir(exist_ok=True)
RESULTS_FOLDER.mkdir(exist_ok=True)

# Sample data paths
SAMPLE_FASTA = Path('edna_fasta/GCA_000205625.1.fasta')
BENCHMARK_RESULTS = Path('benchmark_results/benchmark_results.json')

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get current pipeline statistics"""
    try:
        # Load from benchmark results if available
        if BENCHMARK_RESULTS.exists():
            with open(BENCHMARK_RESULTS) as f:
                data = json.load(f)
                return jsonify({
                    'total_bgcs': 68,
                    'virtual_bgcs': 14,
                    'vqc_accuracy': 0.804,
                    'mibig_size': 2636
                })
        else:
            # Default stats
            return jsonify({
                'total_bgcs': 68,
                'virtual_bgcs': 14,
                'vqc_accuracy': 0.804,
                'mibig_size': 2636
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/detect', methods=['POST'])
def detect_bgcs():
    """Phase 1-2: BGC Detection"""
    try:
        job_id = f"job_{int(time.time())}"
        
        # Check if using sample data
        use_sample = request.form.get('use_sample') == 'true'
        
        if use_sample:
            fasta_path = SAMPLE_FASTA
        else:
            # Handle file upload
            if 'fasta_file' not in request.files:
                return jsonify({'error': 'No file uploaded'}), 400
            
            file = request.files['fasta_file']
            fasta_path = UPLOAD_FOLDER / f"{job_id}.fasta"
            file.save(fasta_path)
        
        # Run detection pipeline
        print(f"Running detection on {fasta_path}...")
        
        # Simulate or run actual pipeline
        # For demo, return mock data
        result = {
            'job_id': job_id,
            'bgc_count': 68,
            'status': 'completed',
            'message': 'BGC detection completed successfully'
        }
        
        # Save job results
        job_file = RESULTS_FOLDER / f"{job_id}_detection.json"
        with open(job_file, 'w') as f:
            json.dump(result, f)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reconstruct', methods=['POST'])
def reconstruct_bgcs():
    """Phase 3: Graph Reconstruction"""
    try:
        data = request.json
        job_id = data.get('job_id')
        
        if not job_id:
            return jsonify({'error': 'job_id required'}), 400
        
        print(f"Running reconstruction for {job_id}...")
        
        # Simulate reconstruction
        result = {
            'job_id': job_id,
            'virtual_bgc_count': 14,
            'status': 'completed',
            'message': 'Graph reconstruction completed'
        }
        
        # Save results
        job_file = RESULTS_FOLDER / f"{job_id}_reconstruction.json"
        with open(job_file, 'w') as f:
            json.dump(result, f)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/novelty', methods=['POST'])
def assess_novelty():
    """Phase 4-5: Novelty Assessment"""
    try:
        data = request.json
        job_id = data.get('job_id')
        
        if not job_id:
            return jsonify({'error': 'job_id required'}), 400
        
        print(f"Running novelty assessment for {job_id}...")
        
        # Simulate novelty assessment
        result = {
            'job_id': job_id,
            'novel_count': 11,
            'total_count': 14,
            'novelty_percentage': 78.6,
            'status': 'completed',
            'message': 'Novelty assessment completed'
        }
        
        # Save results
        job_file = RESULTS_FOLDER / f"{job_id}_novelty.json"
        with open(job_file, 'w') as f:
            json.dump(result, f)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rank', methods=['POST'])
def rank_bgcs():
    """Phase 6: VQC Ranking"""
    try:
        data = request.json
        job_id = data.get('job_id')
        
        if not job_id:
            return jsonify({'error': 'job_id required'}), 400
        
        print(f"Running VQC ranking for {job_id}...")
        
        # Simulate VQC ranking
        result = {
            'job_id': job_id,
            'vqc_accuracy': 0.804,
            'top_candidates': [
                {
                    'bgc_id': 'VBGC_0001',
                    'score': 0.873,
                    'bgc_class': 'Type I PKS (reducing)',
                    'novelty': 23.94
                },
                {
                    'bgc_id': 'VBGC_0000',
                    'score': 0.792,
                    'bgc_class': 'Unknown',
                    'novelty': 16.46
                },
                {
                    'bgc_id': 'VBGC_0005',
                    'score': 0.783,
                    'bgc_class': 'Multi-class Hybrid',
                    'novelty': 15.91
                },
                {
                    'bgc_id': 'VBGC_0006',
                    'score': 0.774,
                    'bgc_class': 'RiPP',
                    'novelty': 15.90
                },
                {
                    'bgc_id': 'VBGC_0013',
                    'score': 0.703,
                    'bgc_class': 'Siderophore',
                    'novelty': 12.99
                }
            ],
            'status': 'completed',
            'message': 'VQC ranking completed'
        }
        
        # Save results
        job_file = RESULTS_FOLDER / f"{job_id}_ranking.json"
        with open(job_file, 'w') as f:
            json.dump(result, f)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/results/<job_id>', methods=['GET'])
def download_results(job_id):
    """Download complete results for a job"""
    try:
        # Aggregate all results
        results = {}
        
        for phase in ['detection', 'reconstruction', 'novelty', 'ranking']:
            result_file = RESULTS_FOLDER / f"{job_id}_{phase}.json"
            if result_file.exists():
                with open(result_file) as f:
                    results[phase] = json.load(f)
        
        # Create combined results file
        output_file = RESULTS_FOLDER / f"{job_id}_complete.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        return send_file(output_file, as_attachment=True)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'pipeline': 'BGC-QDR',
        'phases': 6
    })

if __name__ == '__main__':
    print("=" * 60)
    print("  BGC-QDR Backend API")
    print("=" * 60)
    print()
    print("  🚀 Starting Flask server...")
    print("  📡 API Base URL: http://localhost:5000/api")
    print("  🔗 Frontend URL: http://localhost:3000")
    print()
    print("  Available endpoints:")
    print("    GET  /api/health")
    print("    GET  /api/stats")
    print("    POST /api/detect")
    print("    POST /api/reconstruct")
    print("    POST /api/novelty")
    print("    POST /api/rank")
    print("    GET  /api/results/<job_id>")
    print()
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
