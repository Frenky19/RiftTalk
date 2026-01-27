class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, code: str = 'APP_ERROR'):
        self.message = message
        self.code = code
        super().__init__(self.message)


class DatabaseException(AppException):
    """Exception related to database operations."""

    def __init__(self, message: str, code: str = 'DATABASE_ERROR'):
        super().__init__(message, code)


class VoiceServiceException(AppException):
    """Exception related to voice room service."""

    def __init__(self, message: str, code: str = 'VOICE_SERVICE_ERROR'):
        super().__init__(message, code)


class LCUException(AppException):
    """Exception related to LCU integration."""

    def __init__(self, message: str, code: str = 'LCU_ERROR'):
        super().__init__(message, code)


class WebRTCException(AppException):
    """Exception related to WebRTC."""

    def __init__(self, message: str, code: str = 'WEBRTC_ERROR'):
        super().__init__(message, code)


class AuthenticationException(AppException):
    """Exception related to authentication."""

    def __init__(self, message: str, code: str = 'AUTH_ERROR'):
        super().__init__(message, code)


class ValidationException(AppException):
    """Exception related to data validation."""

    def __init__(self, message: str, code: str = 'VALIDATION_ERROR'):
        super().__init__(message, code)


class DiscordServiceException(AppException):
    """Exception related to Discord service."""

    def __init__(self, message: str, code: str = 'DISCORD_ERROR'):
        super().__init__(message, code)
