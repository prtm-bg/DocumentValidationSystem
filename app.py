# app.py

import sys
from flask import Flask, render_template, request, jsonify, send_file
import cv2
import numpy as np
import gzip
import json
import qrcode
import hashlib
import hmac
import easyocr
import base64
from io import BytesIO
from PIL import Image
import zlib
from pyzbar.pyzbar import decode
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.config import dictConfig
import requests

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize global resources
executor = ThreadPoolExecutor(max_workers=4)
reader = easyocr.Reader(['en'], gpu=False)
SECRET_KEY = b'supersecretkey'  # Should be loaded from environment variable in production

# Cache for optimization
@lru_cache(maxsize=100)
def get_qr_detector():
    return cv2.QRCodeDetector()

@lru_cache(maxsize=1000)
def generate_hash_cached(data_str, dob_month):
    """Cached version of hash generation for repeated values"""
    iterations = int(dob_month) % 10 + 1
    hash_value = data_str.encode()
    for _ in range(iterations):
        hash_value = hmac.new(SECRET_KEY, hash_value, hashlib.sha512).digest()
    return base64.b85encode(hash_value).decode('utf-8')

def optimize_image(image, max_size=(800, 800)):
    """Optimize image size while maintaining readability"""
    if image is None:
        raise ValueError("Invalid image data")
    height, width = image.shape[:2]
    if height > max_size[0] or width > max_size[1]:
        ratio = min(max_size[0]/height, max_size[1]/width)
        new_size = (int(width * ratio), int(height * ratio))
        image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
    return image

def compress_data(data_dict):
    """Improved compression using zlib with optimal settings"""
    json_str = json.dumps(data_dict, separators=(',', ':'))
    compressed = zlib.compress(json_str.encode('utf-8'), level=9)
    return base64.b85encode(compressed).decode('utf-8')

def optimize_for_dense_qr(image):
    """
    Optimize image for dense QR code scanning with ZBar
    """
    # Convert to grayscale if needed
    if len(image.shape) > 2:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # Apply adaptive thresholding to handle varying lighting conditions
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    
    # Sharpen the image to enhance QR code boundaries
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(thresh, -1, kernel)
    
    # Try different sizes to handle dense QR codes
    sizes = [(gray.shape[1], gray.shape[0])]  # Original size
    # Add larger sizes for upscaling if needed
    if gray.shape[1] < 1000 or gray.shape[0] < 1000:
        sizes.append((int(gray.shape[1] * 1.5), int(gray.shape[0] * 1.5)))
    sizes.append((int(gray.shape[1] * 2), int(gray.shape[0] * 2)))
    
    return {
        'original': gray,
        'binary': thresh,
        'sharpened': sharpened,
        'sizes': sizes
    }

@app.route('/api/webcam-qr', methods=['POST'])
def webcam_qr():
    try:
        # Get image data from the request
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
        
        # Use ZBar to decode QR - Try multiple processing techniques
        optimized = optimize_for_dense_qr(image)
        
        # Try different image processing methods to find QR code
        qr_found = False
        qr_data = None
        
        # First try original with various sizes
        for size in optimized['sizes']:
            if size != (image.shape[1], image.shape[0]):
                resized = cv2.resize(optimized['original'], size)
            else:
                resized = optimized['original']
            
            decoded = decode(resized)
            if decoded:
                qr_found = True
                qr_data = decoded[0].data.decode('utf-8')
                logger.info(f"Found QR using original image at size {size}")
                break
        
        # If not found, try binary
        if not qr_found:
            for size in optimized['sizes']:
                if size != (optimized['binary'].shape[1], optimized['binary'].shape[0]):
                    resized = cv2.resize(optimized['binary'], size)
                else:
                    resized = optimized['binary']
                
                decoded = decode(resized)
                if decoded:
                    qr_found = True
                    qr_data = decoded[0].data.decode('utf-8')
                    logger.info(f"Found QR using binary image at size {size}")
                    break
        
        # If still not found, try sharpened
        if not qr_found:
            for size in optimized['sizes']:
                if size != (optimized['sharpened'].shape[1], optimized['sharpened'].shape[0]):
                    resized = cv2.resize(optimized['sharpened'], size)
                else:
                    resized = optimized['sharpened']
                
                decoded = decode(resized)
                if decoded:
                    qr_found = True
                    qr_data = decoded[0].data.decode('utf-8')
                    logger.info(f"Found QR using sharpened image at size {size}")
                    break
        
        # Process QR results
        if qr_found and qr_data:
            # Log the detected QR data for debugging
            logger.info(f"ZBar decoded QR data: {qr_data[:50]}..." if len(qr_data) > 50 else f"ZBar decoded QR data: {qr_data}")
            
            try:
                # Try to process as Aadhaar QR
                formatted_data, raw_data = process_aadhaar_qr(qr_data)
                return jsonify({
                    "type": "aadhaar",
                    "formatted": formatted_data,
                    "raw": raw_data
                })
            except Exception as e:
                logger.info(f"Not an Aadhaar QR, treating as generic. Error: {str(e)}")
                # Return as generic QR data
                return jsonify({
                    "type": "generic",
                    "data": qr_data
                })
        else:
            return jsonify({'message': 'No QR code found'}), 200
        
    except Exception as e:
        logger.error(f"Error in webcam_qr: {str(e)}")
        return jsonify({'error': str(e)}), 500

def process_aadhaar_qr(qr_data):
    """Process Aadhaar QR data with optimized parsing"""
    try:
        byte_array = gzip.decompress(int(qr_data).to_bytes((int(qr_data).bit_length() + 7) // 8, 'big'))
        fields = [f.decode('ISO-8859-1') for f in byte_array.split(b'\xff') if f]
        
        formatted_data = {
            'fullname': fields[3],
            'dob': fields[4],
            'gender': fields[5],
            'address': ' , '.join(fields[i] for i in [8,9,13,7,15,14,6,12,10])
        }
        
        raw_data = '\xff'.join([fields[3], fields[4], fields[5]] + 
                               [fields[i] for i in [8,9,13,7,15,14,6,12,10]])
        
        return formatted_data, raw_data
    except Exception as e:
        logger.error(f"Error processing Aadhaar QR: {str(e)}")
        raise ValueError(f"Invalid Aadhaar QR data: {str(e)}")

def perform_ocr(image):
    """Perform OCR with optimized processing"""
    try:
        image = optimize_image(image)
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

def validate_dob(dob):
    """Validate DOB format and extract month"""
    if not isinstance(dob, str):
        raise ValueError("DOB must be a string")
    
    separators = {'/', '-'}
    separator = next((s for s in separators if s in dob), None)
    
    if not separator:
        raise ValueError("DOB must contain either / or - separators")
    
    parts = dob.split(separator)
    if len(parts) != 3:
        raise ValueError("DOB must be in DD/MM/YYYY or DD-MM-YYYY format")
    
    month = int(parts[1])
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid month value: {month}. Month must be between 1 and 12")
    
    return month

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/verify')
def verify():
    return render_template('verify.html')

@app.route('/api/process-aadhaar', methods=['POST'])
def process_aadhaar():
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
        formatted_data, raw_data = process_aadhaar_qr(data)
        
        return jsonify({"formatted": formatted_data, "raw": raw_data})
    
    except Exception as e:
        logger.error(f"Error in process_aadhaar: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/process-gradecard', methods=['POST'])
def process_gradecard():
    try:
        if 'gradecard_image' not in request.files:
            return jsonify({'error': 'No grade card image provided'}), 400
        
        file = request.files['gradecard_image']
        img_array = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        # Process OCR asynchronously
        future = executor.submit(perform_ocr, img)
        ocr_results = future.result()
        
        # Remove confidence
        for result in ocr_results:
            result.pop('confidence', None)
        
        return jsonify(ocr_results)
    
    except Exception as e:
        logger.error(f"Error in process_gradecard: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-qr', methods=['POST'])
def generate_qr():
    try:
        if not request.is_json:
            return jsonify({'error': 'No JSON data received'}), 400
            
        data = request.get_json()
        if not all(k in data for k in ('aadhaar', 'gradecard')):
            return jsonify({'error': 'Missing required data'}), 400
            
        dob_month = validate_dob(data['aadhaar']['dob'])
        
        # Prepare data for QR
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
        hash_value = generate_hash_cached(json.dumps(combined_data, sort_keys=True), dob_month)
        final_data = b'\xff'.join([str(i).encode('ISO-8859-1') for i in [*combined_data, hash_value]])
        compressed_data = int.from_bytes(gzip.compress(final_data), 'big')
        
        # Store compressed_data as a string for the frontend
        compressed_data_str = str(compressed_data)
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        qr.add_data(compressed_data)
        qr.make(fit=True)
        
        img_buffer = BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Return both the QR image and data in response headers
        response = send_file(
            img_buffer,
            mimetype='image/png',
            as_attachment=False,
            download_name='verification-qr.png'
        )
        
        response.headers.update({
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'X-QR-Data': compressed_data_str  # Add QR data in header
        })
        
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_qr: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/verify-qr', methods=['POST'])
def verify_qr():
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
        aadhaar_data = decoded_data[:4]  # Assuming 4 aadhaar fields
        gradecard_data = decoded_data[4:-3]  # Everything between aadhaar and final fields
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

        # Match hash with hash on block (currently on localhost:6060)
        try:
            blockchain_url = f"http://localhost:6060/api/admin/student/{stored_hash}/transcript"
            response = requests.get(blockchain_url, timeout=5)
            
            if response.status_code == 200:
                blockchain_data = response.json()
                blockchain_details = blockchain_data.get('details')
                logger.info(f"Blockchain verification successful: {blockchain_details}")
                
                # Add blockchain verification results to the response
                combined_data['blockchain_verified'] = True
                combined_data['blockchain_details'] = blockchain_details
            else:
                logger.warning(f"Blockchain verification failed with status code: {response.status_code}")
                combined_data['blockchain_verified'] = False
        except Exception as blockchain_error:
            logger.error(f"Blockchain verification error: {str(blockchain_error)}")
            combined_data['blockchain_verified'] = False
            combined_data['blockchain_error'] = str(blockchain_error)
         
        # Validate hash
        dob_month = validate_dob(combined_data['aadhaar']['dob'])
        computed_hash = generate_hash_cached(
            json.dumps([*aadhaar_data, *gradecard_data, remarks, enrollment], sort_keys=True),
            dob_month
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
    try:
        if 'gradecard_image' not in request.files or 'qr_image' not in request.files:
            return jsonify({'error': 'Both grade card and QR images are required'}), 400
            
        # Get the grade card image
        gradecard_file = request.files['gradecard_image']
        gradecard_array = np.frombuffer(gradecard_file.read(), np.uint8)
        gradecard_img = cv2.imdecode(gradecard_array, cv2.IMREAD_COLOR)
        
        # Get the QR code image directly
        qr_file = request.files['qr_image']
        qr_array = np.frombuffer(qr_file.read(), np.uint8)
        qr_img = cv2.imdecode(qr_array, cv2.IMREAD_COLOR)
        
        # Convert to binary image
        gray = cv2.cvtColor(gradecard_img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY)
        
        # Function to find white rectangle
        def find_rectangle(img, start_y, start_x):
            height, width = img.shape
            end_x = start_x
            end_y = start_y
            
            # Extend vertically
            while end_y < height and img[end_y, start_x] == 255:
                end_y += 1
            
            # Extend horizontally
            can_extend = True
            while end_x < width and can_extend:
                for y in range(start_y, end_y):
                    if img[y, end_x] != 255:
                        can_extend = False
                        break
                if can_extend:
                    end_x += 1
            
            return (start_x, start_y, end_x-1, end_y-1)
        
        # Find largest white rectangle
        height, width = binary.shape
        processed = np.zeros_like(binary)
        max_area = 0
        max_coords = None
        
        for y in range(height):
            for x in range(width):
                if binary[y,x] == 255 and processed[y,x] == 0:
                    x1, y1, x2, y2 = find_rectangle(binary, y, x)
                    area = (x2-x1+1) * (y2-y1+1)
                    if area > max_area:
                        max_area = area
                        max_coords = (x1, y1, x2, y2)
                    processed[y1:y2+1, x1:x2+1] = 255
        
        if not max_coords:
            return jsonify({'error': 'No suitable white space found'}), 400
        
        x1, y1, x2, y2 = max_coords
        rect_width = x2 - x1
        rect_height = y2 - y1

        qr_array = qr_img  # qr_img is already a numpy array from cv2.imdecode
        
        # Resize QR to fit in rectangle (with padding)
        padding = 20
        qr_size = min(rect_width - padding, rect_height - padding)
        if qr_size < 100:  # Minimum size check
            return jsonify({'error': 'White space too small for QR code'}), 400
        
        qr_array = cv2.resize(qr_array, (qr_size, qr_size))
        
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
        gradecard_img[start_y:start_y+qr_size, start_x:start_x+qr_size] = qr_array
        
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
    
if __name__ == '__main__':
    app.run(debug=True)  # Set debug=False in production