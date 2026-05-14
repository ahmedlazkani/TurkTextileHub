# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- Full KAYISOFT API integration with correct 4-header authentication (`Telegram-User-Id`, `Authorization`, `Platform`, `Accept-Language`).
- DeepSeek AI integration for product attribute extraction and validation.
- Multi-language support: Turkish (default), Arabic, English.
- Modular `locales/` directory with JSON translation files.
- `channel_handler.py`: Automatic channel detection when bot is added as admin.
- `deepseek_service.py`: Async DeepSeek client with structured product analysis.
- `kayisoft_api.py`: Full async API client covering all documented KAYISOFT endpoints.
- `product_handler.py`: Step-by-step product creation flow using `ConversationHandler`.
- `start_handler.py`: Account connection flow using deep link tokens.
- `Dockerfile` and `railway.json` for containerized deployment.
- `.env.example` with all required environment variables documented.

### Changed
- Default language changed from Arabic (`ar`) to Turkish (`tr`) across all services and handlers.
- `keyboards.py` refactored to use centralized `get_string()` for all labels.
- `session_manager.py` updated to default to Turkish language.
- `kayisoft_api.py` completely rewritten to use `aiohttp` for async HTTP requests.

### Fixed
- Duplicate keyboard button keys in `keyboards.py`.
- Missing `Platform: telegram` header in all KAYISOFT API requests.

---

## [0.1.0] - 2026-05-14

### Added
- Initial project scaffold with `python-telegram-bot` v20+.
- Basic `/start` command handler.
- BotFather configuration: Description, About, Commands, Menu Button.
- Botpic and Description Picture assets.
