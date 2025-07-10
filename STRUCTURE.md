# Project Structure

```
DocumentValidationSystem/
├── app.py                    # Main Flask application
├── config.py                 # Configuration settings
├── requirements.txt          # Python dependencies
├── runtime.txt              # Python version for deployment
├── Procfile                 # Process file for deployment
├── Dockerfile               # Docker container configuration
├── docker-compose.yml       # Docker Compose for multi-container setup
├── LICENSE                  # MIT License
├── README.md               # Project documentation
├── .gitignore              # Git ignore patterns
├── .gitattributes          # Git attributes
├── static/
│   └── styles.css          # CSS styling
├── templates/
│   ├── index.html          # Main application page
│   └── verify.html         # Verification page
└── utils/
    ├── __init__.py         # Package initialization
    ├── processors.py       # Image and data processing utilities
    └── blockchain.py       # Blockchain verification utilities
```

## File Descriptions

### Core Application Files
- **app.py**: Main Flask application with all API endpoints
- **config.py**: Environment-specific configuration classes
- **requirements.txt**: All Python package dependencies

### Deployment Files
- **Dockerfile**: Container configuration for deployment
- **docker-compose.yml**: Multi-container orchestration
- **Procfile**: Heroku deployment configuration
- **runtime.txt**: Python version specification

### Frontend Files
- **templates/**: HTML templates with embedded JavaScript
- **static/**: CSS and other static assets

### Utility Modules
- **utils/**: Modular helper functions for processing and validation

### Documentation
- **README.md**: Comprehensive project documentation
- **LICENSE**: MIT license for open source distribution
