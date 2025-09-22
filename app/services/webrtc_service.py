import logging
from typing import List, Dict, Any
from app.config import settings
from app.utils.exceptions import WebRTCException

logger = logging.getLogger(__name__)


class WebRTCService:
    def __init__(self):
        self.ice_servers = self._get_ice_servers()

    def _get_ice_servers(self) -> List[Dict[str, Any]]:
        """Получение списка ICE серверов для WebRTC"""
        ice_servers = [
            {
                "urls": [
                    "stun:stun.l.google.com:19302",
                    "stun:stun1.l.google.com:19302",
                    "stun:stun2.l.google.com:19302",
                    "stun:stun3.l.google.com:19302",
                    "stun:stun4.l.google.com:19302"
                ]
            }
        ]
        # Добавляем TURN сервер, если настроен
        if settings.TURN_SERVER_URL:
            turn_server = {
                "urls": [settings.TURN_SERVER_URL],
                "username": settings.TURN_SERVER_USERNAME,
                "credential": settings.TURN_SERVER_PASSWORD
            }
            ice_servers.append(turn_server)
        return ice_servers

    def get_webrtc_config(self, room_id: str) -> Dict[str, Any]:
        """Получение конфигурации WebRTC для комнаты"""
        try:
            return {
                "iceServers": self.ice_servers,
                "iceTransportPolicy": "all",
                "bundlePolicy": "max-bundle",
                "rtcpMuxPolicy": "require",
                "roomId": room_id
            }
        except Exception as e:
            logger.error(f"Failed to generate WebRTC config: {e}")
            raise WebRTCException(f"Failed to generate WebRTC config: {e}")

    def validate_sdp(self, sdp: Dict[str, Any]) -> bool:
        """Валидация SDP предложения/ответа"""
        # Базовая валидация структуры SDP
        required_fields = ["type", "sdp"]
        if not all(field in sdp for field in required_fields):
            return False
        # Проверка допустимых типов
        if sdp["type"] not in ["offer", "answer", "pranswer", "rollback"]:
            return False
        return True

    def generate_stats_report(self) -> Dict[str, Any]:
        """Генерация отчета о статистике WebRTC соединений"""
        # В реальном приложении здесь можно собирать статистику
        # о количестве активных соединений, качестве связи и т.д.
        return {
            "active_connections": 0,  # Заглушка
            "total_rooms": 0,
            "ice_servers": len(self.ice_servers)
        }


# Глобальный экземпляр сервиса
webrtc_service = WebRTCService()
