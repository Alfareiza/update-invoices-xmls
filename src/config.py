import logging
from pathlib import Path

from decouple import config

BASE_DIR: Path = Path(__file__).resolve().parent.parent

# format = r"%(asctime)s - %(levelname)-7s [%(filename)s:%(lineno)03d - %(funcName)34s()] - %(message)s"
format = r"%(asctime)s - %(levelname)-7s [%(filename)-13s:%(lineno)03d - %(funcName)30s()] - %(message)s"
logging.basicConfig(level=logging.INFO, format=format)
for noisy_logger in ["google_auth_httplib2", "googleapiclient"]:
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)
log = logging.getLogger(__name__)


class Config:
    """Static class container for all variables."""
    _BASE_DIR = Path(__file__).resolve().parent.parent

    class DIRECTORIES:
        """Container for any directories you require for your automation.

        Folders will be created automatically
        """

        TEMP =  Path('/tmp')


CONFIG = Config()

if __name__ == '__main__':
    log.info('This is a sample')
    log.warning('This is a longer sample message to show alignment.')
