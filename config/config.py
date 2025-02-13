import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for Maritime Vessel Tracking System"""
    
    # Basic app config
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    APP_NAME = "Maritime Vessel Tracking"
    
    # API URLs
    AIS_BASE_URL = "https://meri.digitraffic.fi/api/ais/v1"
    AIS_LOCATIONS_URL = f"{AIS_BASE_URL}/locations"
    AIS_VESSELS_URL = f"{AIS_BASE_URL}/vessels"
    
    # Database configuration
    DB_USER = os.getenv('POSTGRES_USER', 'admin')
    DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'marine2025')
    DB_HOST = os.getenv('POSTGRES_HOST', 'localhost')
    DB_PORT = os.getenv('POSTGRES_PORT', '5432')
    DB_NAME = os.getenv('POSTGRES_DB', 'maritime_tracking')
    
    # Construct database URL
    SQLALCHEMY_DATABASE_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Data collection settings
    UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', '60'))  # seconds
    BATCH_SIZE = int(os.getenv('BATCH_SIZE', '1000'))
    
    # API settings
    API_PORT = int(os.getenv('API_PORT', '5000'))
    API_HOST = os.getenv('API_HOST', '0.0.0.0')
    
    # Cache settings
    CACHE_TYPE = "simple"
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Logging configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = 'logs/maritime_tracking.log'
    
    # ML Model settings
    MODEL_PATH = 'models/'
    PREDICTION_HORIZON = timedelta(hours=1)
    
    # Map visualization settings
    DEFAULT_CENTER_LAT = 60.1699  # Helsinki
    DEFAULT_CENTER_LON = 24.9384
    DEFAULT_ZOOM = 10
    
    @classmethod
    def get_database_url(cls):
        """Get database URL with password masked for logging purposes"""
        return cls.SQLALCHEMY_DATABASE_URI.replace(cls.DB_PASSWORD, '***')
    
    @classmethod
    def validate(cls):
        """Validate the configuration settings"""
        required_vars = [
            'DB_USER',
            'DB_PASSWORD',
            'DB_HOST',
            'DB_NAME'
        ]
        
        missing_vars = [var for var in required_vars if not getattr(cls, var)]
        
        if missing_vars:
            raise ValueError(f"Missing required configuration variables: {', '.join(missing_vars)}")
            
        return True

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    CACHE_TYPE = "redis"
    
class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:@localhost:5432/maritime_tracking_test'
    
# Configuration dictionary
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

# Get active configuration
active_config = config_by_name[os.getenv('FLASK_ENV', 'default')]