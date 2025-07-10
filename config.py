import os
from datetime import timedelta

class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or b'supersecretkey'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
    
    # OCR Configuration
    OCR_LANGUAGES = ['en']
    OCR_GPU = False
    
    # QR Configuration
    QR_ERROR_CORRECTION = 'L'  # L, M, Q, H
    QR_BOX_SIZE = 10
    QR_BORDER = 4
    
    # Threading Configuration
    MAX_WORKERS = 4
    
    # Cache Configuration
    CACHE_SIZE = 1000
    
    # Blockchain Configuration
    BLOCKCHAIN_URL = os.environ.get('BLOCKCHAIN_URL') or 'http://localhost:6060'
    BLOCKCHAIN_TIMEOUT = 5

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # Production security settings
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)

class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    TESTING = True
    WTF_CSRF_ENABLED = False

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
