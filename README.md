# Anime Suggest Bot

بات پیشنهاد انیمه با دو زبان فارسی و انگلیسی، پوستر واقعی و توضیحات زیر عکس.

## قابلیت‌های جدید / Discovery features

- `/genre` — یک ژانر انتخاب کنید تا همان لحظه یک پیشنهاد تصادفی بگیرید. «پیشنهاد بعدی» در همان ژانر می‌ماند. Your saved genre stays the same, and your rating and episode filters still apply.

- `/search Naruto` — جستجوی عنوان؛ یا اسم انیمه را مستقیم بفرستید. نتایج صفحه‌بندی دارند و با زدن هر عنوان، پوستر و توضیحات نمایش داده می‌شود. جستجو فیلم و ویژه‌برنامه را هم شامل می‌شود. Use English titles or Japanese romanization.
- `/top` — انیمه‌های تلویزیونی با بالاترین امتیاز، با صفحه‌بندی.
- `/airing` — انیمه‌های تلویزیونی در حال پخش، به ترتیب ترند.
- `/settings` — ذخیرهٔ ژانر، حداقل امتیاز و حداکثر تعداد قسمت برای هر کاربر. این تنظیمات روی پیشنهاد تصادفی، برترین‌ها و در حال پخش اعمال می‌شوند؛ جستجوی عنوان مستقل است. عنوان‌هایی که تعداد قسمت یا امتیازشان مشخص نیست ممکن است با فیلتر عددی حذف شوند.
- `/history` — فهرست دیده‌شده‌ها با امکان لغو ثبت اشتباه. لغو، عنوان را به لیست تماشا برنمی‌گرداند.
- `/stats` — تعداد دیده‌شده‌ها، لیست تماشا و عنوان‌های کشف‌شده.
- `/export` — دانلود لیست تماشا، دیده‌شده‌ها و تنظیمات خودتان به شکل JSON؛ فایل توکن یا اطلاعات دیگران را ندارد. This is a personal export; importing is not implemented.
- `/cancel` — خروج از حالت جستجو. منوی اصلی فارسی/انگلیسی و منوی دستورات تلگرام هم به‌روز شده‌اند.

Search and related-result cards have independent watchlist buttons. Watched titles are marked ✅ in search/browse results. Interactive discovery controls expire after a bot restart; rerun the command to get fresh buttons. Saved lists, history, language and preferences remain in SQLite.

API fields and filters follow the [official AniList query reference](https://docs.anilist.co/reference/query).

## Windows local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Save `TELEGRAM_BOT_TOKEN=...` in `.env`. If needed, put `TELEGRAM_PROXY_URL=http://127.0.0.1:10808` in `run.env`; the local proxy must be running. Both files are ignored by Git.

Double-click `start-bot.cmd` to run in the background or `stop-bot.cmd` to stop it. These scripts check this project's full script path to avoid starting duplicate instances or stopping unrelated Python programs. For status:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bot.ps1 status
```

Logs are in `bot.stderr.log` and `bot.stdout.log`. The computer must stay awake and connected. The scripts do not configure startup at Windows sign-in. Send `/help` to refresh an existing Telegram keyboard.

## Render Free deployment

Use a Python web service with build command `pip install -r requirements.txt` and start command `python -u animeSuggest.py`. Leave Health Check Path blank for Render's TCP check. Render supplies `PORT` and `RENDER_EXTERNAL_URL`.

Add `TELEGRAM_BOT_TOKEN`, a TLS-enabled `DATABASE_URL` from a persistent Postgres provider such as Neon, and a random `TELEGRAM_WEBHOOK_SECRET` (32–256 letters, digits, hyphens or underscores). Keep the laptop's proxy settings out of the Render environment. The app registers its Telegram webhook automatically. Render Free sleeps after inactivity, so the first reply can be delayed.

To preserve existing data, stop the local bot at cutover and run `.\.venv\Scripts\python.exe migrate_to_postgres.py` before deploying. The script prompts for the connection string or reads `DATABASE_URL` from the ignored local `.env.render` file. It copies a SQLite snapshot and leaves existing cloud rows intact on re-run. If you return to local polling, suspend the Render service first so both copies cannot claim the same bot.

Run all offline tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -q
```

## اجرا

```bash
cd /home/saman/Desktop/AnimeBot
source .venv/bin/activate
python animeSuggest.py
```

برای نصب اولیه، محیط مجازی پایتون بسازید و `pip install -r requirements.txt` را اجرا کنید. اگر اتصال PyPI مشکل داشت:

```bash
python -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

توکن در `.env` و پروکسی در `run.env` قرار می‌گیرد. نام متغیرها در `.env.example` آمده است. متغیرهای محیطی اولویت دارند؛ سپس `run.env` و بعد `.env` خوانده می‌شوند. برای تنظیم پروکسی جداگانهٔ عکس‌ها و سرویس انیمه، `ANIME_PROXY_URL` را تعریف کنید. در تنظیم فعلی، Xray روی پورت `10808` باید روشن باشد.

## استفاده

- `/start`: انتخاب زبان با پرچم، سپس نمایش منوی همان زبان.
- `/suggest`: دریافت پیشنهاد؛ کاربر جدید ابتدا باید زبان انتخاب کند.
- «دیدم»: ثبت به‌عنوان دیده‌شده و پیشنهاد بعدی.
- «🍿 بعداً می‌بینم»: ذخیرهٔ انیمه در لیست شخصی تماشا، بدون ثبت به‌عنوان دیده‌شده.
- `/watchlist` یا «📋 لیست تماشای من»: نمایش عنوان‌های ذخیره‌شده با صفحه‌بندی، دکمهٔ حذف و «دیدم». حذف، انیمه را دیده‌شده نمی‌کند؛ «دیدم» آن را از لیست حذف و به سابقهٔ دیده‌شده‌ها اضافه می‌کند. لیست هر کاربر مستقل است و پس از راه‌اندازی دوباره باقی می‌ماند. برای نمایش دکمهٔ جدید در منوی قبلی، `/help` را بزنید.
- «پیشنهاد بعدی»: پیشنهاد دیگر بدون ثبت به‌عنوان دیده‌شده.
- «انیمه‌های مرتبط»: نمایش آثار تلویزیونیِ همان مجموعه و انیمه‌های مشابه، همراه پوستر و توضیحات به زبان انتخاب‌شده؛ در هر نوبت حداکثر سه مورد.
- «موارد مرتبط بیشتر»: ادامهٔ نتایج همان عنوان، بدون تکرار موارد نمایش‌داده‌شده. دیده‌شده‌ها از این نتایج هم کنار گذاشته می‌شوند. دکمه‌های هر کارت مستقل‌اند و می‌توان از هر مورد، انیمه‌های مرتبط با خودش را دید.
- `/language`: تغییر زبان؛ `/help`: راهنما.

از میان ۵۰ انیمهٔ تلویزیونی ترند AniList، ۲۵ مورد دارای پوستر و بالاترین امتیاز انتخاب می‌شوند. فصل‌ها با دنبال‌کردن ارتباط فصل‌های قبلی و بعدی شمرده می‌شوند؛ بخش‌های جداگانه نیز جدا حساب می‌شوند. دادهٔ ناقص با عبارت «حداقل» نمایش داده می‌شود.

زبان، سابقهٔ نمایش و دیده‌شده‌ها و ترجمه‌های موفق در `animebot.sqlite3` ذخیره می‌شوند. پاک‌کردن این فایل، این اطلاعات را بازنشانی می‌کند. اطلاعات هر کاربر جداست. داده‌های سرویس انیمه ۱۵ دقیقه کش می‌شوند.

ترجمهٔ خلاصه‌های کوتاه با MyMemory انجام می‌شود؛ این سرویس محدودیت مصرف دارد. ترجمه‌های موفق ذخیره و دوباره استفاده می‌شوند. در حالت فارسی، خرابی ترجمه باعث نمایش پیام فارسی و گزینهٔ تلاش مجدد می‌شود؛ خلاصهٔ انگلیسی جایگزین نمی‌شود. اگر منبع فقط شمارهٔ فصل را اعلام کرده باشد و خلاصهٔ داستانی نداشته باشد، این موضوع به فارسی توضیح داده می‌شود.

## بررسی

```bash
.venv/bin/python -m unittest test_animeSuggest.py
```

تست‌ها آفلاین‌اند؛ از دیتابیس موقت و پیام‌های شبیه‌سازی‌شده استفاده می‌کنند و پیامی در تلگرام نمی‌فرستند.
