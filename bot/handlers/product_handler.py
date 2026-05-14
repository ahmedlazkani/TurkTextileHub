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
from bot.services.session_manager import get_user_lang

logger = logging.getLogger(__name__)

# States for the ConversationHandler
SELECT_CATEGORY, SELECT_SUBCATEGORY, FILL_FORM, UPLOAD_IMAGES, CONFIRM = range(5)

async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the product addition flow by asking for the main category."""
    user_id = str(update.effective_user.id)
    lang = get_user_lang(user_id) or "tr"
    
    # TODO: Fetch categories from KAYISOFT API
    # Mock categories for now
    categories = [
        {"id": "1", "name": "Erkek Giyim" if lang == "tr" else "Men's Clothing"},
        {"id": "2", "name": "Kadın Giyim" if lang == "tr" else "Women's Clothing"},
    ]
    
    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(cat["name"], callback_data=f"cat_{cat['id']}")])
        
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
    
    # TODO: Fetch subcategories from KAYISOFT API based on cat_id
    # Mock subcategories
    subcategories = [
        {"id": "101", "name": "Tişört" if lang == "tr" else "T-Shirt"},
        {"id": "102", "name": "Pantolon" if lang == "tr" else "Pants"},
    ]
    
    keyboard = []
    for sub in subcategories:
        keyboard.append([InlineKeyboardButton(sub["name"], callback_data=f"sub_{sub['id']}")])
        
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
    
    # TODO: Fetch attributes for this subcategory from KAYISOFT API
    # Ask user to provide details
    await query.edit_message_text(get_string(lang, "add_product_fill_form"))
    
    return FILL_FORM

async def handle_form_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives form text, analyzes with DeepSeek, and asks for images."""
    user_id = str(update.effective_user.id)
    lang = get_user_lang(user_id) or "tr"
    text = update.message.text
    
    # TODO: Send text to DeepSeek for analysis and attribute extraction
    # Mock AI analysis
    context.user_data['product_details'] = text
    
    await update.message.reply_text(get_string(lang, "add_product_upload_images"))
    return UPLOAD_IMAGES

async def handle_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives images and asks for final confirmation."""
    user_id = str(update.effective_user.id)
    lang = get_user_lang(user_id) or "tr"
    
    if 'images' not in context.user_data:
        context.user_data['images'] = []
        
    if update.message.photo:
        # Get the highest resolution photo
        photo_file_id = update.message.photo[-1].file_id
        context.user_data['images'].append(photo_file_id)
        
    # In a real scenario, we'd wait for a "Done" button or timeout
    # For simplicity, we proceed after 1 image
    
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
        # TODO: Upload images to S3 via KAYISOFT API
        # TODO: Create product via KAYISOFT API
        # TODO: Publish to Telegram Channel
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
