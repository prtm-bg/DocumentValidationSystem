"""Blockchain integration utilities."""

import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BlockchainVerifier:
    """Handles blockchain verification operations."""
    
    def __init__(self, base_url: str, timeout: int = 5):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    def verify_hash(self, hash_value: str) -> Dict[str, Any]:
        """Verify hash against blockchain records."""
        try:
            url = f"{self.base_url}/api/admin/student/{hash_value}/transcript"
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                blockchain_data = response.json()
                return {
                    'verified': True,
                    'details': blockchain_data.get('details'),
                    'data': blockchain_data
                }
            else:
                logger.warning(f"Blockchain verification failed with status {response.status_code}")
                return {
                    'verified': False,
                    'error': f"HTTP {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Blockchain verification error: {str(e)}")
            return {
                'verified': False,
                'error': str(e)
            }
