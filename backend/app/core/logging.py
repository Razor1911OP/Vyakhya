"""
Vyakhya Logging
Privacy-aware structured logging - NEVER logs raw message text
"""
import logging
import sys
from pythonjsonlogger import jsonlogger
from typing import Any, Dict


class RedactedFormatter(jsonlogger.JsonFormatter):
    """JSON formatter that prevents accidental PII logging"""
    
    REDACTED_KEYS = {
        'message_text', 'raw_text', 'sms_content', 
        'otp', 'account_number', 'card_number', 
        'phone', 'vpa', 'password', 'pin'
    }
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        
        # Redact sensitive fields
        for key in list(log_record.keys()):
            if key.lower() in self.REDACTED_KEYS:
                log_record[key] = "[REDACTED]"
        
        # Add standard fields
        log_record['logger'] = record.name
        log_record['level'] = record.levelname


def setup_logging(log_level: str = "INFO") -> None:
    """Configure application-wide logging"""
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Console handler with JSON formatting
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = RedactedFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s',
        timestamp=True
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Silence noisy libraries
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("torch").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module"""
    return logging.getLogger(name)
