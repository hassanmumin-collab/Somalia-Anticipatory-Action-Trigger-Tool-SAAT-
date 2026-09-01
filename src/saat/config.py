"""
Configuration management for SAAT.

Handles path resolution and .env settings. Never uses __file__ math.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class Config:
    """Configuration container for SAAT."""

    def __init__(self, env_file: Optional[Path] = None):
        """
        Initialize configuration.

        Args:
            env_file: Path to .env file. If None, searches in project root.
        """
        # Determine project root by searching upward for pyproject.toml
        self.project_root = self._find_project_root()
        
        # Set config and data directories
        self.config_dir = self.project_root / "config"
        self.data_dir = self.project_root / "data"
        self.logs_dir = self.project_root / "logs"
        
        # Load environment variables
        if env_file is None:
            env_file = self.project_root / ".env"
        
        if env_file.exists():
            load_dotenv(env_file)
        
        # API keys and credentials (from .env)
        self.chirps_url = "https://data.chc.ucsb.edu"
        self.frrims_url = os.getenv("FRRIMS_URL", "http://frrims.faoswalim.org/rivers/levels")
        self.hapi_url = os.getenv("HAPI_URL", "https://hapi.humdata.org/api/v2")
        self.hapi_app_identifier = os.getenv("HAPI_APP_IDENTIFIER")
        self.ckan_url = os.getenv("CKAN_URL", "https://data.humdata.org/api/3/action")
        
        self.acled_key = os.getenv("ACLED_KEY")
        self.cds_key = os.getenv("CDS_KEY")
        self.cdse_username = os.getenv("CDSE_USERNAME")
        self.cdse_password = os.getenv("CDSE_PASSWORD")
        
        # Operational settings
        self.verbosity = os.getenv("SAAT_VERBOSITY", "INFO")
        self.log_file = self.logs_dir / "saat.log"

    @staticmethod
    def _find_project_root() -> Path:
        """
        Find project root by searching upward for pyproject.toml.

        Returns:
            Path to project root.

        Raises:
            FileNotFoundError: If pyproject.toml is not found.
        """
        current = Path.cwd()
        for parent in [current] + list(current.parents):
            if (parent / "pyproject.toml").exists():
                return parent
        raise FileNotFoundError("Could not find project root (pyproject.toml not found)")

    def ensure_dirs(self) -> None:
        """Create necessary directories if they don't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        """String representation of configuration."""
        return f"Config(project_root={self.project_root}, verbosity={self.verbosity})"


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Reset global configuration (for testing)."""
    global _config
    _config = None
