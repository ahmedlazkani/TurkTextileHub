# TopKap Telegram Bot 🇹🇷

![TopKap Banner](https://via.placeholder.com/800x400.png?text=TopKap+Telegram+Bot)

TopKap is a professional Telegram bot designed for Turkish textile wholesale suppliers. It provides a seamless, mobile-app-like experience for suppliers to manage their products, connect their Telegram channels, and publish products directly to their audience.

## 🌟 Features

- **Multi-language Support:** Turkish (Default), Arabic, and English.
- **Professional UX:** Interactive inline keyboards, clear navigation, and emoji-supported UI.
- **AI-Powered Product Entry:** Uses DeepSeek AI to analyze user input and automatically extract product attributes.
- **KAYISOFT API Integration:** Fully integrated with KAYISOFT backend for categories, attributes, and product management.
- **Channel Management:** Suppliers can connect their Telegram channels and publish products directly from the bot.
- **Docker Ready:** Easy deployment using Docker and Railway.

## 🏗 Architecture

The bot is built using `python-telegram-bot` (v20+) and follows a modular architecture:

- `bot/main.py`: Entry point and handler registration.
- `bot/handlers/`: Contains handlers for different flows (start, product, channel).
- `bot/services/`: Contains business logic (KAYISOFT API, DeepSeek AI, Language, Session).
- `bot/locales/`: Contains JSON files for multi-language support.
- `bot/keyboards.py`: Centralized keyboard generation for consistent UX.

## 🚀 Deployment

### Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- KAYISOFT API Base URL
- DeepSeek API Key

### Environment Variables

Create a `.env` file in the root directory:

```env
BOT_TOKEN=your_telegram_bot_token
KAYISOFT_API_URL=https://api-wholesale.dev.kayisoft.net
DEEPSEEK_API_KEY=your_deepseek_api_key
ADMIN_TELEGRAM_ID=your_telegram_id
```

### Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the bot:
   ```bash
   python -m bot.main
   ```

### Railway Deployment

This repository is configured for seamless deployment on [Railway](https://railway.app/).
Simply connect your GitHub repository to Railway, and it will automatically build and deploy using the provided `Dockerfile` and `railway.json`.

## 📚 API Integration (KAYISOFT)

The bot communicates with the KAYISOFT backend using the following headers for all requests:

- `Telegram-User-Id`: The Telegram ID of the user.
- `Authorization`: Bearer token (obtained during the connection flow).
- `Platform`: `telegram`
- `Accept-Language`: The user's selected language code (`tr`, `ar`, `en`).

## 📄 License

Proprietary - All rights reserved to TopKap & KAYISOFT.
