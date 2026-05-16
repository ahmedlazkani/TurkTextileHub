"""
bot/handlers/product_handler.py
===============================
Handles the product addition flow:
Category selection -> Attribute form -> AI Analysis -> Image upload -> Publish
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ConversationHandler
from bot.services.language_service import get_string
from bot.services.language_service import get_user_lang
from bot.services.kayisoft_api import KayisoftAPI
from bot.services.deepseek_service import deepseek_service

logger = logging.getLogger(__name__)

# States for the ConversationHandler
SELECT_CATEGORY, SELECT_SUBCATEGORY, FILL_FORM, UPLOAD_IMAGES, CONFIRM = range(5)

async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the product addition flow by asking for the main category."""
    user_id = str(update.effective_user.id)
    lang = get_user_lang(user_id) or "tr"
    
    api = KayisoftAPI(telegram_user_id=user_id, language=lang)
    categories = await api.get_categories(parent_id="")
    
    if not categories:
        text = get_string(lang, "error_fetching_categories") if get_string(lang, "error_fetching_categories") else "Kategoriler alınamadı. Lütfen hesabınızı bağladığınızdan emin olun."
        if update.message:
            await update.message.reply_text(text)
        else:
            await update.callback_query.message.reply_text(text)
        return ConversationHandler.END
        
    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(cat.get("name", "Unknown"), callback_data=f"cat_{cat.get('id')}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(get_string(lang, "add_product_select_category"), reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text(get_string(lang, "add_product_select_category"), reply_markup=reply_markup)
        
    return SELECT_CATEGORY

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles category selection and asks for subcategory."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    lang = get_user_lang(user_id) or "tr"
    cat_id = query.data.split("_")[1]
    context.user_data['selected_category'] = cat_id
    
    api = KayisoftAPI(telegram_user_id=user_id, language=lang)
    subcategories = await api.get_categories(parent_id=cat_id)
    
    if not subcategories:
        await query.edit_message_text("Alt kategoriler bulunamadı. / Subcategories not found.")
        return ConversationHandler.END
        
    keyboard = []
    for sub in subcategories:
        keyboard.append([InlineKeyboardButton(sub.get("name", "Unknown"), callback_data=f"sub_{sub.get('id')}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(get_string(lang, "add_product_select_subcategory"), reply_markup=reply_markup)
    
    return SELECT_SUBCATEGORY

async def handle_subcategory_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles subcategory selection and asks user to fill the form."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    lang = get_user_lang(user_id) or "tr"
    sub_id = query.data.split("_")[1]
    context.user_data['selected_subcategory'] = sub_id
    
    api = KayisoftAPI(telegram_user_id=user_id, language=lang)
    attributes = await api.get_attributes(category_id=sub_id)
    
    if attributes:
        context.user_data['expected_attributes'] = [attr.get('name') for attr in attributes]
    else:
        context.user_data['expected_attributes'] = ["Renk", "Beden", "Kumaş"] # Fallback
        
    await query.edit_message_text(get_string(lang, "add_product_fill_form"))
    
    return FILL_FORM

async def handle_form_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives form text, analyzes with DeepSeek, and asks for images."""
    user_id = str(update.effective_user.id)
    lang = get_user_lang(user_id) or "tr"
    text = update.message.text
    
    expected_attrs = context.user_data.get('expected_attributes', [])
    
    processing_msg = await update.message.reply_text("⏳ Yapay zeka analiz ediyor... / AI is analyzing...")
    
    extracted_data = await deepseek_service.analyze_product_text(text, expected_attrs)
    
    context.user_data['product_details'] = extracted_data or {"raw_text": text}
    
    await processing_msg.delete()
    await update.message.reply_text(get_string(lang, "add_product_upload_images"))
    return UPLOAD_IMAGES

async def handle_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives images and asks for final confirmation."""
    user_id = str(update.effective_user.id)
    lang = get_user_lang(user_id) or "tr"
    
    if 'images' not in context.user_data:
        context.user_data['images'] = []
        
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
        context.user_data['images'].append(photo_file_id)
        
    keyboard = [
        [InlineKeyboardButton("✅ Evet / Yes", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ İptal / Cancel", callback_data="confirm_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(get_string(lang, "add_product_confirm"), reply_markup=reply_markup)
    return CONFIRM

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles final confirmation and publishes the product."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    lang = get_user_lang(user_id) or "tr"
    
    if query.data == "confirm_yes":
        await query.edit_message_text("⏳ Ürün yükleniyor... / Publishing product...")
        
        # Here we would:
        # 1. Download images from Telegram
        # 2. Get signed URLs from KAYISOFT
        # 3. Upload images to S3
        # 4. Create product via KAYISOFT API
        # 5. Publish to Telegram Channel
        
        await query.edit_message_text(get_string(lang, "add_product_success"))
    else:
        await query.edit_message_text("İşlem iptal edildi. / Operation cancelled.")
        
    context.user_data.clear()
    return ConversationHandler.END

def get_product_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^(➕ Ürün Ekle|➕ Add Product|➕ إضافة منتج)$'), start_add_product),
            CommandHandler('add_product', start_add_product)
        ],
        states={
            SELECT_CATEGORY: [CallbackQueryHandler(handle_category_selection, pattern="^cat_")],
            SELECT_SUBCATEGORY: [CallbackQueryHandler(handle_subcategory_selection, pattern="^sub_")],
            FILL_FORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_form_input)],
            UPLOAD_IMAGES: [MessageHandler(filters.PHOTO, handle_image_upload)],
            CONFIRM: [CallbackQueryHandler(handle_confirmation, pattern="^confirm_")]
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)]
    )
