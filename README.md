# Document Validation System

A comprehensive web-based system for processing, validating, and verifying Aadhaar cards and grade cards using QR code technology.

## Features

- **Aadhaar QR Processing**: Extract and validate information from Aadhaar QR codes
- **Grade Card OCR**: Extract text elements from grade card images using OCR technology
- **QR Code Generation**: Create secure verification QR codes with embedded document data
- **Document Verification**: Verify the authenticity of documents using generated QR codes
- **QR Code Embedding**: Automatically embed verification QR codes into grade card images
- **Webcam Support**: Real-time QR code scanning using device camera
- **Blockchain Integration**: Optional blockchain verification for enhanced security

## Technology Stack

- **Backend**: Python Flask
- **Computer Vision**: OpenCV, EasyOCR
- **QR Processing**: pyzbar, qrcode
- **Image Processing**: Pillow, NumPy
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/DocumentValidationSystem.git
   cd DocumentValidationSystem
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   python app.py
   ```

5. **Access the application**
   Open your browser and navigate to `http://localhost:5000`

## Usage

### Document Processing
1. **Aadhaar Processing**: Upload an Aadhaar QR code image or use webcam to scan
2. **Grade Card Processing**: Upload a grade card image for OCR text extraction
3. **QR Generation**: Generate a verification QR code containing both document data
4. **QR Embedding**: Automatically embed the verification QR into the grade card

### Document Verification
1. Navigate to `/verify` endpoint
2. Upload a verification QR code image or scan using webcam
3. View extracted and verified document information

## API Endpoints

- `POST /api/process-aadhaar` - Process Aadhaar QR code
- `POST /api/process-gradecard` - Extract text from grade card using OCR
- `POST /api/generate-qr` - Generate verification QR code
- `POST /api/verify-qr` - Verify document authenticity
- `POST /api/embed-qr` - Embed QR code into grade card
- `POST /api/webcam-qr` - Process QR code from webcam feed

## Configuration

### Environment Variables
```bash
export SECRET_KEY="your-secret-key-here"
export FLASK_ENV="production"  # For production deployment
```

### Production Deployment
- Set `debug=False` in app.py
- Configure proper secret key
- Use production WSGI server (gunicorn, uWSGI)
- Enable HTTPS

## Security Features

- HMAC-based hash verification
- Secure data compression using zlib
- Base85 encoding for data integrity
- Input validation and sanitization
- Error handling and logging

## Browser Compatibility

- Chrome 60+
- Firefox 55+
- Safari 11+
- Edge 16+

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- OpenCV community for computer vision tools
- EasyOCR team for OCR capabilities
- Flask team for the web framework