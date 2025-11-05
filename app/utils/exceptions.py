class AppException(Exception):
    """Базовое исключение приложения"""
    def __init__(self, message: str, code: str = "APP_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class DatabaseException(AppException):
    """Исключение, связанное с операциями базы данных"""
    def __init__(self, message: str, code: str = "DATABASE_ERROR"):
        super().__init__(message, code)


class VoiceServiceException(AppException):
    """Исключение, связанное с сервисом голосовых комнат"""
    def __init__(self, message: str, code: str = "VOICE_SERVICE_ERROR"):
        super().__init__(message, code)


class LCUException(AppException):
    """Исключение, связанное с интеграцией LCU"""
    def __init__(self, message: str, code: str = "LCU_ERROR"):
        super().__init__(message, code)


class WebRTCException(AppException):
    """Исключение, связанное с WebRTC"""
    def __init__(self, message: str, code: str = "WEBRTC_ERROR"):
        super().__init__(message, code)


class AuthenticationException(AppException):
    """Исключение, связанное с аутентификацией"""
    def __init__(self, message: str, code: str = "AUTH_ERROR"):
        super().__init__(message, code)


class ValidationException(AppException):
    """Исключение, связанное с валидацией данных"""
    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        super().__init__(message, code)


class DiscordServiceException(AppException):
    """Исключение, связанное с сервисом Discord"""
    def __init__(self, message: str, code: str = "DISCORD_ERROR"):
        super().__init__(message, code)
