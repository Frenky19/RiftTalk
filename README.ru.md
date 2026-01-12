# LoL Voice Chat Desktop (командный голосовой чат через Discord)

[English](README.md) | [Русский](README.ru.md)

Windows‑приложение, которое автоматически объединяет игроков одной команды (которые тоже запустили приложение) в временные Discord‑голосовые каналы **в момент начала матча** и полностью очищает всё **после окончания матча**.

> **Strict mode**: приложение требует успешного подключения к Discord‑боту на старте.

---

## Что делает приложение

- Отслеживает состояние матча через **League Client (LCU)** на Windows.
- При старте матча:
  - Создаёт временный **голосовой канал** для Blue/Red команды.
  - Выдаёт доступ через роли/права.
  - Перемещает/подключает привязанных пользователей в нужный канал.
- После окончания матча:
  - Снимает роли / выгоняет пользователей из временного канала.
  - Удаляет временные каналы.
- Есть встроенный интерфейс на WebView.

---

## Требования

- **Windows 10/11**
- **Python 3.11+** (рекомендуется) или собранная версия (см. Build)
- **Discord‑сервер**, где у вас есть права добавлять бота и управлять каналами/ролями
- Установленная League of Legends и запущенный **League Client**

---

## Быстрый старт (разработка)

1) Виртуальное окружение и зависимости

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) Создайте `.env` в корне проекта (см. переменные ниже)

3) Запуск

```bash
python webview_app.py
```

---

## Переменные окружения

Создайте `.env` в корне проекта:

```ini
# Обязательные (strict mode)
DISCORD_BOT_TOKEN=ВАШ_ТОКЕН_БОТА
DISCORD_GUILD_ID=ID_ВАШЕГО_СЕРВЕРА

# Опционально (рекомендуется)
DISCORD_CATEGORY_ID=ID_КАТЕГОРИИ_ДЛЯ_КАНАЛОВ       # куда создавать временные каналы
DISCORD_OAUTH_CLIENT_ID=CLIENT_ID_OAUTH            # если используете привязку аккаунта
DISCORD_OAUTH_CLIENT_SECRET=CLIENT_SECRET_OAUTH
DISCORD_OAUTH_REDIRECT_URI=http://127.0.0.1:PORT/discord/callback

# Поведение приложения
DEBUG=false
REDIS_URL=memory://                                # по умолчанию: in-memory storage
```

Примечания:
- Если Redis недоступен, приложение может работать с in‑memory хранилищем.
- Если обязательных Discord‑переменных нет или бот не подключается, приложение **не стартует**.

---

## Настройка Discord‑бота

1) Создайте приложение в Discord Developer Portal, добавьте **Bot**.
2) Включите **Privileged Gateway Intents**, если требуется логикой проекта:
   - *Server Members Intent* (часто нужен для надёжной работы с участниками/перемещением)
3) Выдайте права боту:
   - Manage Channels
   - Manage Roles
   - Move Members
   - View Channels
   - Connect / Speak
4) Пригласите бота на сервер.

Важно: роль бота должна быть **выше** ролей, которыми он управляет (role hierarchy).

---


## Build (сборка)

В репозитории есть скрипты для сборки Windows‑версии (конкретные шаги зависят от выбранного инструмента, например PyInstaller).

Типовой запуск:

```bash
python build.py
```

Если меняете build‑пайплайн — сохраняйте **strict mode** (без «тихих» фоллбеков при проблемах с Discord).

---

## Troubleshooting (частые проблемы)

### Старт падает: “Discord connection failed”
- Проверьте `DISCORD_BOT_TOKEN` и `DISCORD_GUILD_ID`
- Убедитесь, что бот добавлен на сервер и онлайн
- Проверьте права в категории/каналах и иерархию ролей

### Не находится LCU
- Запустите League Client и убедитесь, что существует `lockfile`
- Запускайте приложение с тем же уровнем прав, что и клиент (не смешивайте Admin/не‑Admin)

---

## Безопасность

- Никогда не коммитьте `.env` и токены бота.
- Для локального OAuth используйте redirect на `127.0.0.1`.

---

## Вклад в проект

PR приветствуются:
- фиксы и рефакторинг
- улучшение логирования/диагностики
- улучшения UI/UX WebView

---

## Лицензия

```
MIT License

Copyright (c) 2026 Frenky19

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
