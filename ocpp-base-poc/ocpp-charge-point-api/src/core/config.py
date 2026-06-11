import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "OCPP Charge Point API")
    VERSION: str = os.getenv("VERSION", "1.0.0")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "t")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./test.db")  # Example default value

config = Config()