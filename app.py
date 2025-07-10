"""Document Validation System - Main Application Module.

A Flask web application for processing and validating Aadhaar cards and grade cards
using QR code technology with OCR capabilities.
"""

import os
import json
import logging
import base64
import gzip
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import cv2
import numpy as np
import qrcode
import easyocr
import requests
from flask import Flask, render_template, request, jsonify, send_file
from pyzbar.pyzbar import decode

from config import config
from utils import (
    ImageProcessor, DataProcessor, AadhaarProcessor, 
    Validator, QRCodeEmbedder, BlockchainVerifier
)

def create_app(config_name=None):
    """Application factory pattern for creating Flask app."""
    app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    
    # Configure logging
    configure_logging(app)
    
    return app

def configure_logging(app):
    """Configure application logging."""
    if not app.debug and not app.testing:
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )

# Create application instance
app = create_app()
logger = logging.getLogger(__name__)

# Initialize global resources
executor = ThreadPoolExecutor(max_workers=app.config['MAX_WORKERS'])
reader = easyocr.Reader(app.config['OCR_LANGUAGES'], gpu=app.config['OCR_GPU'])
blockchain_verifier = BlockchainVerifier(
    app.config['BLOCKCHAIN_URL'], 
    app.config['BLOCKCHAIN_TIMEOUT']
)

# Initialize processors
image_processor = ImageProcessor()
data_processor = DataProcessor()
aadhaar_processor = AadhaarProcessor()
validator = Validator()
qr_embedder = QRCodeEmbedder()

@lru_cache(maxsize=100)
def get_qr_detector():
    """Get cached QR code detector instance."""
    return cv2.QRCodeDetector()

def perform_ocr(image):
    """Perform OCR with optimized processing."""
    try:
        image = image_processor.optimize_image(image)
        results = reader.readtext(image)
        
        return [{
            'text': text,
            'position': {
                'x': int(coords[0][0]),
                'y': int(coords[0][1]),
                'width': int(coords[2][0] - coords[0][0]),
                'height': int(coords[2][1] - coords[0][1])
            },
            'confidence': conf
        } for coords, text, conf in results if text.strip()]
    except Exception as e:
        logger.error(f"OCR processing error: {str(e)}")
        raise

@app.route('/')
def index():
    """Render main application page."""
    return render_template('index.html')

@app.route('/verify')
def verify():
    """Render verification page."""
    return render_template('verify.html')

@app.route('/api/webcam-qr', methods=['POST'])
def webcam_qr():
    """Process QR code from webcam feed."""
    try:
        # Get image data from request
        image_data = request.json.get('image')
        if not image_data:
            return jsonify({'error': 'No image data provided'}), 400
        
        # Convert base64 to image
        image_data = image_data.split(',')[1] if ',' in image_data else image_data
        img_bytes = base64.b64decode(image_data)
        img_array = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({'error': 'Failed to decode image'}), 400
        
        # Optimize image for QR scanning
        optimized = image_processor.optimize_for_qr_scanning(image)
        
        # Try different processing methods to find QR code
        qr_found = False
        qr_data = None
        
        # Try different image variations and sizes
        for img_type in ['original', 'binary', 'sharpened']:
            if qr_found:
                break
            
            for size in optimized['sizes']:
                current_img = optimized[img_type]
                if size != (current_img.shape[1], current_img.shape[0]):
                    resized = cv2.resize(current_img, size)
                else:
                    resized = current_img
                
                decoded = decode(resized)
                if decoded:
                    qr_found = True
                    qr_data = decoded[0].data.decode('utf-8')
                    logger.info(f"Found QR using {img_type} image at size {size}")
                    break
        
        # Process QR results
        if qr_found and qr_data:
            logger.info(f"ZBar decoded QR data: {qr_data[:50]}...")
            
            try:
                # Try to process as Aadhaar QR
                formatted_data, raw_data = aadhaar_processor.process_qr_data(qr_data)
                return jsonify({
                    "type": "aadhaar",
                    "formatted": formatted_data,
                    "raw": raw_data
                })
            except Exception as e:
                logger.info(f"Not an Aadhaar QR, treating as generic. Error: {str(e)}")
                return jsonify({
                    "type": "generic",
                    "data": qr_data
                })
        else:
            return jsonify({'message': 'No QR code found'}), 200
        
    except Exception as e:
        logger.error(f"Error in webcam_qr: {str(e)}")
        return jsonify({'error': str(e)}), 500
@app.route('/api/process-aadhaar', methods=['POST'])
def process_aadhaar():
    """Process Aadhaar QR code from uploaded image."""
    try:
        if 'qr_image' not in request.files:
            return jsonify({'error': 'No QR image provided'}), 400
        
        file = request.files['qr_image']
        img_array = np.frombuffer(file.read(), np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({'error': 'Unable to read image'}), 400
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        qr_codes = decode(gray)
        
        if not qr_codes:
            return jsonify({'error': 'No QR code detected'}), 400
        
        data = qr_codes[0].data.decode('utf-8')
        formatted_data, raw_data = aadhaar_processor.process_qr_data(data)
        
        return jsonify({"formatted": formatted_data, "raw": raw_data})
    
    except Exception as e:
        logger.error(f"Error in process_aadhaar: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/process-gradecard', methods=['POST'])
def process_gradecard():
    """Process grade card image using OCR."""
    try:
        if 'gradecard_image' not in request.files:
            return jsonify({'error': 'No grade card image provided'}), 400
        
        file = request.files['gradecard_image']
        img_array = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        # Process OCR asynchronously
        future = executor.submit(perform_ocr, img)
        ocr_results = future.result()
        
        # Remove confidence scores from results
        for result in ocr_results:
            result.pop('confidence', None)
        
        return jsonify(ocr_results)
    
    except Exception as e:
        logger.error(f"Error in process_gradecard: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-qr', methods=['POST'])
def generate_qr():
    """Generate verification QR code from document data."""
    try:
        if not request.is_json:
            return jsonify({'error': 'No JSON data received'}), 400
            
        data = request.get_json()
        if not all(k in data for k in ('aadhaar', 'gradecard')):
            return jsonify({'error': 'Missing required data'}), 400
            
        dob_month = validator.validate_dob(data['aadhaar']['dob'])
        
        # Prepare data for QR code
        combined_data = [
            *[str(v) for v in data['aadhaar'].values()],
            *[
                str([
                    item['position']['x'],
                    item['position']['y'],
                    item['position']['width'],
                    item['position']['height'],
                    item['text']
                ])
                for item in data['gradecard']
            ],
            str(data.get('remarks', '')),
            str(data.get('enrollment', ''))
        ]
        
        # Generate hash and compress data
        hash_value = data_processor.generate_hash(
            json.dumps(combined_data, sort_keys=True), 
            dob_month, 
            app.config['SECRET_KEY']
        )
        final_data = b'\xff'.join([str(i).encode('ISO-8859-1') for i in [*combined_data, hash_value]])
        compressed_data = int.from_bytes(gzip.compress(final_data), 'big')
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=None,
            error_correction=getattr(qrcode.constants, f"ERROR_CORRECT_{app.config['QR_ERROR_CORRECTION']}"),
            box_size=app.config['QR_BOX_SIZE'],
            border=app.config['QR_BORDER'],
        )
        
        qr.add_data(compressed_data)
        qr.make(fit=True)
        
        img_buffer = BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Return QR image
        response = send_file(
            img_buffer,
            mimetype='image/png',
            as_attachment=False,
            download_name='verification-qr.png'
        )
        
        response.headers.update({
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'X-QR-Data': str(compressed_data)
        })
        
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_qr: {str(e)}")
        return jsonify({'error': str(e)}), 500
@app.route('/api/verify-qr', methods=['POST'])
def verify_qr():
    """Verify document authenticity from QR code."""
    try:
        if 'qr_image' not in request.files:
            return jsonify({'error': 'No QR image provided'}), 400
        
        file = request.files['qr_image']
        img_array = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        detector = get_qr_detector()
        data, _, _ = detector.detectAndDecode(img)
        
        if not data:
            return jsonify({'error': 'No QR code detected'}), 400
        
        # Process QR data
        byte_data = int(data).to_bytes((int(data).bit_length() + 7) // 8, 'big')
        decoded_data = gzip.decompress(byte_data).decode('ISO-8859-1').split('\xff')
        
        # Extract components
        aadhaar_data = decoded_data[:4]
        gradecard_data = decoded_data[4:-3]
        remarks = decoded_data[-3]
        enrollment = decoded_data[-2]
        stored_hash = decoded_data[-1]
        
        # Reconstruct data for verification
        combined_data = {
            'aadhaar': dict(zip(['address', 'dob', 'fullname', 'gender'], aadhaar_data)),
            'gradecard': gradecard_data,
            'remarks': remarks,
            'enrollment': enrollment
        }

        # Blockchain verification
        blockchain_result = blockchain_verifier.verify_hash(stored_hash)
        combined_data['blockchain_verified'] = blockchain_result['verified']
        
        if blockchain_result['verified']:
            combined_data['blockchain_details'] = blockchain_result.get('details')
            logger.info("Blockchain verification successful")
        else:
            combined_data['blockchain_error'] = blockchain_result.get('error')
            logger.warning(f"Blockchain verification failed: {blockchain_result.get('error')}")
         
        # Validate hash
        dob_month = validator.validate_dob(combined_data['aadhaar']['dob'])
        computed_hash = data_processor.generate_hash(
            json.dumps([*aadhaar_data, *gradecard_data, remarks, enrollment], sort_keys=True),
            dob_month,
            app.config['SECRET_KEY']
        )
        
        combined_data['gradecard'] = [eval(i) for i in gradecard_data]
        
        return jsonify({
            'is_valid': computed_hash == stored_hash,
            'data': combined_data if computed_hash == stored_hash else None
        })
    
    except Exception as e:
        logger.error(f"Error in verify_qr: {str(e)}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/embed-qr', methods=['POST'])
def embed_qr():
    """Embed QR code into grade card image."""
    try:
        if 'gradecard_image' not in request.files or 'qr_image' not in request.files:
            return jsonify({'error': 'Both grade card and QR images are required'}), 400
            
        # Get the grade card image
        gradecard_file = request.files['gradecard_image']
        gradecard_array = np.frombuffer(gradecard_file.read(), np.uint8)
        gradecard_img = cv2.imdecode(gradecard_array, cv2.IMREAD_COLOR)
        
        # Get the QR code image
        qr_file = request.files['qr_image']
        qr_array = np.frombuffer(qr_file.read(), np.uint8)
        qr_img = cv2.imdecode(qr_array, cv2.IMREAD_COLOR)
        
        # Convert to binary image for white space detection
        gray = cv2.cvtColor(gradecard_img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY)
        
        # Find largest white rectangle
        max_coords = qr_embedder.find_largest_white_space(binary)
        
        if not max_coords:
            return jsonify({'error': 'No suitable white space found'}), 400
        
        x1, y1, x2, y2 = max_coords
        rect_width = x2 - x1
        rect_height = y2 - y1

        # Resize QR to fit in rectangle with padding
        padding = 20
        qr_size = min(rect_width - padding, rect_height - padding)
        if qr_size < 100:
            return jsonify({'error': 'White space too small for QR code'}), 400
        
        qr_img = cv2.resize(qr_img, (qr_size, qr_size))
        
        # Calculate centering position
        start_x = x1 + (rect_width - qr_size) // 2
        start_y = y1 + (rect_height - qr_size) // 2
        
        # Add white background for QR code
        cv2.rectangle(
            gradecard_img,
            (start_x-5, start_y-5),
            (start_x+qr_size+5, start_y+qr_size+5),
            (255, 255, 255),
            -1
        )
        
        # Embed QR code
        gradecard_img[start_y:start_y+qr_size, start_x:start_x+qr_size] = qr_img
        
        # Add border around QR code
        cv2.rectangle(
            gradecard_img,
            (start_x-5, start_y-5),
            (start_x+qr_size+5, start_y+qr_size+5),
            (0, 0, 0),
            2
        )
        
        # Return modified image
        _, img_encoded = cv2.imencode('.jpg', gradecard_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        io_buf = BytesIO(img_encoded.tobytes())
        
        return send_file(
            io_buf,
            mimetype='image/jpeg',
            as_attachment=True,
            download_name='gradecard_with_qr.jpg'
        )
    
    except Exception as e:
        logger.error(f"Error in embed_qr: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)