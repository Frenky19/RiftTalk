import os
import aiohttp
from typing import Optional, Dict, Any
from app.utils.exceptions import LCUException


class LCUConnector:
    def __init__(self):
        self.lockfile_path = self._get_lockfile_path()
        self.lockfile_data: Optional[Dict[str, str]] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_connected_flag = False

    def _get_lockfile_path(self) -> str:
        """Получение пути к lockfile клиента League of Legends"""
        # Стандартный путь для Windows
        base_path = os.getenv("LOCALAPPDATA", "")
        return os.path.join(
            base_path, "Riot Games", "Riot Client", "Config", "lockfile"
        )

    def is_connected(self) -> bool:
        """Проверка подключения к LCU"""
        return self.is_connected_flag and self.session is not None

    async def connect(self) -> bool:
        """Подключение к League Client UX API"""
        try:
            # Проверяем наличие lockfile
            if not os.path.exists(self.lockfile_path):
                raise LCUException(
                    "Lockfile not found. Is the client running?"
                )
            # Читаем данные из lockfile
            with open(self.lockfile_path, 'r') as f:
                lockfile_content = f.read().strip()
                parts = lockfile_content.split(':')
                if len(parts) < 5:
                    raise LCUException("Invalid lockfile format")
                self.lockfile_data = {
                    "process_name": parts[0],
                    "pid": parts[1],
                    "port": parts[2],
                    "password": parts[3],
                    "protocol": parts[4]
                }
            # Создаем сессию для запросов
            self.session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth('riot', self.lockfile_data['password']),
                connector=aiohttp.TCPConnector(verify_ssl=False),
                headers={'Content-Type': 'application/json'}
            )
            # Проверяем подключение
            test_url = f"{self.lockfile_data['protocol']}://127.0.0.1:{self.lockfile_data['port']}/lol-summoner/v1/current-summoner"
            async with self.session.get(test_url) as response:
                if response.status == 200:
                    self.is_connected_flag = True
                    return True
                else:
                    raise LCUException(
                        f"LCU connection test failed: {response.status}"
                    )
        except Exception as e:
            self.is_connected_flag = False
            if self.session:
                await self.session.close()
                self.session = None
            raise LCUException(f"Failed to connect to LCU: {str(e)}")

    async def disconnect(self):
        """Отключение от LCU"""
        if self.session:
            await self.session.close()
            self.session = None
        self.is_connected_flag = False

    async def make_request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Any] = None) -> Any:
        """Выполнение запроса к LCU API"""
        if not self.is_connected():
            raise LCUException("Not connected to LCU")
        url = f"{self.lockfile_data['protocol']}://127.0.0.1:{self.lockfile_data['port']}{endpoint}"
        try:
            async with self.session.request(method, url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 204:
                    return None
                else:
                    raise LCUException(
                        f"LCU API error: {response.status} - {await response.text()}"
                    )
        except Exception as e:
            raise LCUException(f"Request to LCU API failed: {str(e)}")

    async def get_current_summoner(self) -> Optional[Dict[str, Any]]:
        """Получение информации о текущем призывателе"""
        return await self.make_request(
            "GET", "/lol-summoner/v1/current-summoner"
        )

    async def get_game_flow_phase(self) -> Optional[str]:
        """Получение текущей фазы игрового процесса"""
        phase_data = await self.make_request(
            "GET", "/lol-gameflow/v1/gameflow-phase"
        )
        return phase_data if isinstance(phase_data, str) else None

    async def get_chat_me(self) -> Optional[Dict[str, Any]]:
        """Получение информации о текущем пользователе в чате"""
        return await self.make_request("GET", "/lol-chat/v1/me")


# Глобальный экземпляр коннектора
lcu_connector = LCUConnector()
