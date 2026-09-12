# تسليم DevOps وتشغيل بوت TopKap على خادم الشركة

**الغرض:** هذا الدليل هو مرجع التشغيل والنقل لفريق DevOps. المستودع يحتوي الكود وملفات الحاوية فقط؛ أما جميع المفاتيح وملفات الحالة التشغيلية فتُدار خارج GitHub وخارج صورة Docker.

> **قاعدة أمان غير قابلة للتفاوض:** لا يُرفع ملف `.env`، ولا أي مفتاح API أو Bot Token أو ملف بيانات إنتاج إلى GitHub أو إلى Docker image أو إلى المحادثات. يحقن DevOps الأسرار وقت التشغيل فقط.

## 1. البنية التشغيلية المعتمدة

| المكوّن | المسؤولية | ملاحظة تشغيلية |
|---|---|---|
| `topkap-bot` | FastAPI وTelegram long polling ضمن عملية واحدة | يشغّل **نسخة واحدة فقط** في الإنتاج. |
| Reverse proxy | TLS، الدومين العام، وتمرير الطلبات إلى `127.0.0.1:8080` | يجب أن يوفّر HTTPS قبل تفعيل Mini App. |
| Docker volume `topkap_data` | اللغات، القنوات، sentinel التقارير الأسبوعية | يُركّب داخل الحاوية على `/data`. |
| KAYISOFT API | الفئات والخصائص والمنتجات والوسائط | يحتاج رابط الإنتاج والمفتاح الصحيحين. |
| مزود AI | استخراج بيانات المنتج وتوليد بوست القناة | يتطلب DeepSeek أو مزود fallback مفعّل. |

البوت يعتمد Telegram **polling**. لذلك لا يجوز تشغيل Railway وخادم الشركة في الوقت نفسه باستخدام الرمز نفسه؛ تشغيل عمليتي polling متزامنتين يسبب تضارباً في استقبال التحديثات. يُنفّذ التحويل ضمن نافذة صيانة قصيرة بعد اكتمال اختبار الخادم الجديد.

## 2. ما هو موجود في المستودع

| الملف | دوره |
|---|---|
| `Dockerfile` | صورة إنتاج مبنية على Python 3.11، تعمل بمستخدم غير جذري وتحتوي healthcheck. |
| `docker-compose.yml` | مرجع تشغيل لخادم الشركة: volume دائم، منفذ محلي، healthcheck، وقيود أمنية. |
| `.dockerignore` | يمنع نسخ الأسرار وGit والسجلات وبيانات التشغيل إلى صورة Docker. |
| `.env.example` | أسماء المتغيرات المطلوبة فقط مع قيم placeholders غير صالحة للإنتاج. |
| `requirements.txt` | تبعيات Python المقفلة بالإصدارات. |
| `docs/AI_COLLABORATION_WORKFLOW.md` | فصل صلاحيات الذكاء الاصطناعي عن DevOps والإنتاج. |

## 3. متغيرات البيئة

ينشئ DevOps الملف `/opt/topkap-bot/.env` من `.env.example`، ويمنحه صلاحيات مالك الخدمة فقط (`chmod 600`). لا تُدرج القيم في تذاكر العمل أو اللقطات أو السجلات.

| المتغير | التصنيف | مطلوب | الغرض |
|---|---:|---:|---|
| `APP_ENV` | تشغيلي | نعم | يضبط على `production` في خادم الشركة لتفعيل فحص الإعدادات قبل بدء الخدمة. |
| `PUBLIC_BASE_URL` | تشغيلي | نعم | عنوان HTTPS الخارجي، مثل `https://bot.company.example`. |
| `TELEGRAM_BOT_TOKEN` | سر | نعم | رمز Telegram Bot. |
| `ADMIN_TELEGRAM_ID` | معرّف تشغيلي | نعم | معرّف مسؤول التنبيهات. |
| `KAYISOFT_API_URL` | تشغيلي | نعم | رابط KAYISOFT للإنتاج. |
| `KAYISOFT_API_TOKEN` | سر | نعم | اعتماد KAYISOFT server-to-server. |
| `DEEPSEEK_API_KEY` | سر | نعم لميزة الإدخال المدعوم بالذكاء الاصطناعي | اعتماد مزود AI الأساسي. |
| `TOPKAP_APP_URL` و`TOPGATE_WEB_URL` | تشغيلي | نعم | روابط التطبيقات/الصفحات العامة. |
| `TELEGRAM_BOT_CONNECT_BASE_URL` | تشغيلي | نعم | رابط ربط المورد ببوت Telegram. |
| `CHANNELS_FILE` و`LANGS_FILE` | تشغيلي | نعم | يجب أن يشيرا إلى `/data/user_channels.json` و`/data/user_langs.json`. |
| `KAYISOFT_WEBHOOK_SECRET` | سر | عند تفعيل KAYISOFT webhook | تحقق من طلبات webhook. |
| `ORDERS_WEBHOOK_SECRET` | سر | عند تفعيل orders webhook | تحقق من طلبات orders webhook. |
| `OPENAI_API_KEY` و`OPENAI_BASE_URL` | سر/تشغيلي | اختياري | مزود AI احتياطي. |

> استخدم الأسماء الأساسية أعلاه في الخادم الجديد. الأسماء القديمة مثل `BOT_TOKEN` و`RAILWAY_DOMAIN` و`KAYISOFT_API_KEY` موجودة فقط للتوافق المؤقت مع النشر السابق ولا تُعتمد في إعداد جديد.

## 4. تجهيز الخادم

يفترض هذا المرجع Ubuntu حديثاً مع Docker Engine وDocker Compose plugin وNginx أو reverse proxy مكافئ. يُنشأ مستخدم خدمة محدود الصلاحية ومجلد تشغيل مملوك له:

```bash
sudo install -d -o "$USER" -g "$USER" -m 0750 /opt/topkap-bot
cd /opt/topkap-bot
git clone https://github.com/ahmedlazkani/TurkTextileHub.git .
cp .env.example .env
chmod 600 .env
```

يضع DevOps القيم الفعلية في `.env` عبر secret manager أو إجراء إداري آمن. بعد ذلك يجب فحص صيغة Compose من دون تشغيل الخدمة:

```bash
docker compose --env-file .env config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
curl --fail --silent http://127.0.0.1:8080/health
```

النتيجة الصحيحة لنقطة الصحة هي JSON يحتوي `status: "ok"` و`bot_running: true`.

## 5. إعداد Reverse Proxy وTLS

لا يعرّض Compose المنفذ إلا محلياً افتراضياً. يمرّر Nginx الطلبات إلى الحاوية عبر `127.0.0.1:8080`، ويكون `PUBLIC_BASE_URL` مطابقاً تماماً للدومين الخارجي وHTTPS.

```nginx
server {
    listen 443 ssl http2;
    server_name bot.company.example;

    # يدار TLS وفق معيار الشركة، مثل certbot أو load balancer.
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

بعد تفعيل TLS، يتحقق DevOps من:

```bash
curl --fail --silent https://bot.company.example/health
```

## 6. نقل بيانات التشغيل من Railway

البيانات الحالية في Railway Volume ليست جزءاً من GitHub. قبل التحويل، يصدّر DevOps ملفات `/data/user_channels.json` و`/data/user_langs.json` و`/data/.last_weekly_stats` من الـ Volume الحالي إلى قناة نقل آمنة، ثم يستوردها إلى volume الشركة. لا تُرسل هذه الملفات في المحادثات أو البريد العام لأنها تحتوي معرّفات تشغيلية للمستخدمين والقنوات.

مثال احتياطي محلي للـ volume على خادم الشركة:

```bash
mkdir -p backups
chmod 700 backups
docker run --rm \
  -v topkap_data:/data:ro \
  -v "$(pwd)/backups":/backup \
  alpine tar czf /backup/topkap_data_"$(date +%F)".tgz -C /data .
```

يُشفّر DevOps النسخ الاحتياطية ويحتفظ بها وفق سياسة الشركة. لا يستخدم الأمر `docker compose down -v` في الإنتاج، لأنه يحذف الـ volume وبيانات التشغيل.

## 7. خطة التحويل من Railway

| المرحلة | مسؤول التنفيذ | الإجراء | معيار النجاح |
|---|---|---|---|
| 1. Preflight | DevOps | بناء الصورة، فحص `.env`، تحقق `/health` على الخادم الجديد | الحاوية `healthy` و`bot_running: true` في بيئة اختبار مع رمز اختبار منفصل إن أمكن. |
| 2. TLS وMini App | DevOps | تفعيل الدومين وHTTPS ومطابقة `PUBLIC_BASE_URL` | يفتح `/webapp/product-form` عبر HTTPS. |
| 3. نقل الحالة | DevOps | استيراد ملفات `/data` وامتلاكها من volume | تبقى لغة المورد وقنواته بعد إعادة تشغيل الحاوية. |
| 4. Cutover | DevOps | إيقاف polling في Railway أولاً، ثم تشغيل نسخة الشركة | لا يوجد سوى poller واحد للرمز، وتعمل `/health`. |
| 5. Smoke test | QA/حسام | `/start`، فتح النموذج، إنشاء مسودة، صورة لكل لون، Regenerate، نشر اختبار | لا يوجد `Product session expired` أو خلط صور أو IDs خام. |
| 6. Rollback | DevOps | إيقاف نسخة الشركة ثم إعادة تشغيل Railway أو النسخة السابقة | لا تشغّل النسختين معاً. |

## 8. التشغيل والصيانة

| العملية | الأمر |
|---|---|
| عرض الحالة | `docker compose ps` |
| عرض آخر السجلات | `docker compose logs --tail=200 topkap-bot` |
| إعادة تشغيل مقصودة | `docker compose restart topkap-bot` |
| نشر إصدار تمت مراجعته | `git fetch --all --prune && git checkout <approved-commit> && docker compose build --pull && docker compose up -d` |
| تحقق بعد النشر | `curl --fail --silent http://127.0.0.1:8080/health` |
| استعادة نسخة volume | يتبع إجراء DevOps الداخلي بعد إيقاف الحاوية وأخذ نسخة احتياطية جديدة أولاً. |

لا تسجل الحاوية رموز Telegram أو قيم متغيرات البيئة. مع ذلك، يجب تدوير أي secret ظهر سابقاً في Railways logs أو لقطات شاشة قبل النقل النهائي.

## 9. قيود تشغيلية مقصودة

البوت والـ FastAPI موجودان في عملية واحدة؛ لذلك `--workers 1` مقصود. لا ترفع عدد replicas أو workers لهذا service، لأن Telegram polling يتطلب مستهلكاً واحداً للتحديثات. إذا احتاجت المنصة توسعاً أفقياً لاحقاً، يفصل DevOps طبقة polling إلى worker واحد، مع وضع WebApp خلف خدمة HTTP قابلة للتوسع وتبديل JSON إلى قاعدة بيانات مشتركة.

## 10. ملاحظات أمنية قبل التسليم

المستودع الحالي عام. لا تُغيّر خصوصيته أو صلاحياته ضمن هذا التسليم من دون قرار مالك المشروع، لكن يوصى بشدة بتحويله إلى **Private** أو وضعه داخل GitHub Organization الخاصة بالشركة قبل منح أي صلاحية كتابة. يجب كذلك تشغيل secret scanning في GitHub، وتدوير أي اعتماد ظهر في سجل Git أو سجلات Railway سابقاً.

## المراجع

[1] [Docker Compose: production considerations](https://docs.docker.com/compose/production/)

[2] [Dockerfile reference: HEALTHCHECK](https://docs.docker.com/reference/dockerfile/#healthcheck)

[3] [Telegram Bot API](https://core.telegram.org/bots/api)
