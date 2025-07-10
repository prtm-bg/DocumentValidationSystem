"""Utility functions for document processing and validation."""

import cv2
import numpy as np
import gzip
import json
import hashlib
import hmac
import base64
import zlib
from functools import lru_cache
from typing import Dict, List, Tuple, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ImageProcessor:
    """Handles image processing operations."""
    
    @staticmethod
    def optimize_image(image: np.ndarray, max_size: Tuple[int, int] = (800, 800)) -> np.ndarray:
        """Optimize image size while maintaining readability."""
        if image is None:
            raise ValueError("Invalid image data")
        
        height, width = image.shape[:2]
        if height > max_size[0] or width > max_size[1]:
            ratio = min(max_size[0]/height, max_size[1]/width)
            new_size = (int(width * ratio), int(height * ratio))
            image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
        
        return image
    
    @staticmethod
    def optimize_for_qr_scanning(image: np.ndarray) -> Dict[str, Any]:
        """Optimize image for dense QR code scanning."""
        if len(image.shape) > 2:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Sharpen the image
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(thresh, -1, kernel)
        
        # Generate different sizes for upscaling
        sizes = [(gray.shape[1], gray.shape[0])]
        if gray.shape[1] < 1000 or gray.shape[0] < 1000:
            sizes.append((int(gray.shape[1] * 1.5), int(gray.shape[0] * 1.5)))
        sizes.append((int(gray.shape[1] * 2), int(gray.shape[0] * 2)))
        
        return {
            'original': gray,
            'binary': thresh,
            'sharpened': sharpened,
            'sizes': sizes
        }

class DataProcessor:
    """Handles data compression, decompression, and hashing."""
    
    @staticmethod
    def compress_data(data_dict: Dict[str, Any]) -> str:
        """Compress data using zlib with optimal settings."""
        json_str = json.dumps(data_dict, separators=(',', ':'))
        compressed = zlib.compress(json_str.encode('utf-8'), level=9)
        return base64.b85encode(compressed).decode('utf-8')
    
    @staticmethod
    @lru_cache(maxsize=1000)
    def generate_hash(data_str: str, dob_month: int, secret_key: bytes) -> str:
        """Generate secure hash with DOB-based iterations."""
        iterations = int(dob_month) % 10 + 1
        hash_value = data_str.encode()
        
        for _ in range(iterations):
            hash_value = hmac.new(secret_key, hash_value, hashlib.sha512).digest()
        
        return base64.b85encode(hash_value).decode('utf-8')

class AadhaarProcessor:
    """Handles Aadhaar QR code processing."""
    
    @staticmethod
    def process_qr_data(qr_data: str) -> Tuple[Dict[str, str], str]:
        """Process Aadhaar QR data and extract information."""
        try:
            byte_array = gzip.decompress(
                int(qr_data).to_bytes((int(qr_data).bit_length() + 7) // 8, 'big')
            )
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

class Validator:
    """Handles data validation."""
    
    @staticmethod
    def validate_dob(dob: str) -> int:
        """Validate DOB format and extract month."""
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
            raise ValueError(f"Invalid month value: {month}")
        
        return month
    
    @staticmethod
    def is_allowed_file(filename: str, allowed_extensions: set) -> bool:
        """Check if file extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in allowed_extensions

class QRCodeEmbedder:
    """Handles QR code embedding into documents."""
    
    @staticmethod
    def find_white_rectangle(binary_img: np.ndarray, start_y: int, start_x: int) -> Tuple[int, int, int, int]:
        """Find the largest white rectangle starting from given coordinates."""
        height, width = binary_img.shape
        end_x = start_x
        end_y = start_y
        
        # Extend vertically
        while end_y < height and binary_img[end_y, start_x] == 255:
            end_y += 1
        
        # Extend horizontally
        can_extend = True
        while end_x < width and can_extend:
            for y in range(start_y, end_y):
                if binary_img[y, end_x] != 255:
                    can_extend = False
                    break
            if can_extend:
                end_x += 1
        
        return (start_x, start_y, end_x-1, end_y-1)
    
    @staticmethod
    def find_largest_white_space(binary_img: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Find the largest white rectangular space in the image."""
        height, width = binary_img.shape
        processed = np.zeros_like(binary_img)
        max_area = 0
        max_coords = None
        
        for y in range(height):
            for x in range(width):
                if binary_img[y,x] == 255 and processed[y,x] == 0:
                    x1, y1, x2, y2 = QRCodeEmbedder.find_white_rectangle(binary_img, y, x)
                    area = (x2-x1+1) * (y2-y1+1)
                    if area > max_area:
                        max_area = area
                        max_coords = (x1, y1, x2, y2)
                    processed[y1:y2+1, x1:x2+1] = 255
        
        return max_coords
