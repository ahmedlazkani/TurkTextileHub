<div align="center">
  <img src="https://via.placeholder.com/800x200.png?text=TopKap+Telegram+Bot" alt="TopKap Banner">
  
  # TopKap Telegram Bot 🇹🇷
  
  **The Ultimate Wholesale Textile Hub for Turkish Suppliers**
  
  [![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
  [![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-v20%2B-blue.svg)](https://core.telegram.org/bots/api)
  [![Deployment](https://img.shields.io/badge/Deployment-Docker%20%2B%20DevOps-2496ED.svg)](docs/DEVOPS_HANDOVER.md)
  [![License](https://img.shields.io/badge/License-Proprietary-red.svg)](#)
</div>

---

## 📖 Overview

**TopKap Telegram Bot** is a professional, enterprise-grade Telegram bot designed specifically for Turkish textile wholesale suppliers. It acts as a seamless bridge between the TopKap mobile application and the Telegram ecosystem, allowing suppliers to manage their products, connect their Telegram channels, and publish directly to their audience with an intuitive, app-like experience.

Built with modern asynchronous Python (`python-telegram-bot` v20+), it features deep integration with the **KAYISOFT Backend API** and leverages **DeepSeek AI** for intelligent product attribute extraction.

---

## ✨ Key Features

- 🌍 **Multilingual Support:** Fully localized in Turkish (Default), Arabic, and English with dynamic language switching.
- 🤖 **AI-Powered Product Entry:** Uses DeepSeek LLM to automatically extract categories, subcategories, and attributes from natural language input.
- 🔗 **Seamless Account Linking:** Secure deep-link token authentication connecting the Telegram bot to the TopKap App.
- 📢 **Automated Channel Management:** Automatically detects when added as a channel admin and registers the channel for direct product publishing.
- 🎨 **Professional UX/UI:** Rich HTML formatting, interactive inline keyboards, and emoji-supported navigation.
- 🚀 **Enterprise Architecture:** Modular design, robust error handling, and containerized deployment ready for scale.

---

## 🏗 System Architecture

The bot follows a highly modular, service-oriented architecture to ensure maintainability and scalability.

![System Architecture](docs/architecture.png)

### Core Components:
1. **Handlers (`bot/handlers/`):** Manage specific user flows (Start, Product Creation, Channel Management).
2. **Services (`bot/services/`):** Encapsulate business logic:
   - `KayisoftAPI`: Async HTTP client for backend communication with strict 4-header authentication.
   - `DeepSeekService`: AI integration for natural language processing.
   - `LanguageService`: Dynamic localization engine.
3. **Locales (`bot/locales/`):** JSON-based translation files for TR, AR, and EN.

---

## 🔄 Connection Flow

The account linking and channel connection process is designed for maximum security and user convenience.

![Connection Flow](docs/flow.png)

### 1. Account Linking
1. Supplier clicks "Connect Telegram" in the TopKap App.
2. App generates a short-lived JWT token (15m expiry).
3. App opens Telegram via deep link: `tg://resolve?domain=TopKapTR_bot&start=TOKEN`.
4. Bot receives the token, validates it via KAYISOFT API, and links the account.

### 2. Channel Connection
1. Supplier adds the bot to their Telegram channel as an Administrator.
2. Bot detects the `my_chat_member` event.
3. Bot automatically registers the channel ID and Name with the KAYISOFT API.
4. Supplier receives a localized success message and can start publishing.

---

## 🚀 Deployment Guide

The project is containerized for company-managed infrastructure. The production deployment contract is:

- `Dockerfile` builds a non-root Python 3.11 image with a `/health` check.
- `docker-compose.yml` is the reference deployment for a single Telegram polling instance, persistent `/data`, and a reverse proxy terminating TLS.
- `.env.example` contains **names and placeholders only**. The actual `.env` is owned by DevOps, ignored by Git, and never copied into the image.

> Run exactly **one** Telegram polling instance for a bot token. Do not keep Railway and the company server polling concurrently during cutover.

### Quick local validation

```bash
git clone https://github.com/ahmedlazkani/TurkTextileHub.git
cd TurkTextileHub
cp .env.example .env
# Fill .env locally; never commit it.
docker compose --env-file .env config --quiet
docker compose up --build
```

### Authoritative operations documentation

| Document | Purpose |
|---|---|
| [`docs/DEVOPS_HANDOVER.md`](docs/DEVOPS_HANDOVER.md) | Server preparation, secrets, Docker, TLS, data migration, cutover, rollback, and operations. |
| [`docs/AI_COLLABORATION_WORKFLOW.md`](docs/AI_COLLABORATION_WORKFLOW.md) | Change-management policy: AI/GitHub access only; DevOps owns secrets and production deployment. |
| [`.env.example`](.env.example) | Environment-variable names, categorization, and safe placeholders. |

---

## 📚 API Integration Details

All requests to the KAYISOFT API are authenticated using a strict 4-header system:

| Header | Description |
|--------|-------------|
| `Telegram-User-Id` | The unique Telegram ID of the user making the request. |
| `Authorization` | Bearer token for API access. |
| `Platform` | Always set to `telegram`. |
| `Accept-Language` | The user's selected language (`tr`, `ar`, `en`). |

*Note: The API client includes automatic sanitization to prevent HTTP header injection vulnerabilities.*

---

## 📄 License

**Proprietary Software**  
All rights reserved to **TopKap** & **KAYISOFT**. Unauthorized copying, modification, or distribution of this software is strictly prohibited.
