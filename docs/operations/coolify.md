# Flow2API у Coolify

Використовуйте `docker-compose.coolify.yml` як Docker Compose файл ресурсу з Git-репозиторію. Цей варіант запускає **API**, зберігає SQLite у томі `flow2api_data`, а згенеровані медіафайли у `flow2api_tmp`. Він не публікує порт безпосередньо на хості: налаштуйте домен для сервісу `flow2api` з внутрішнім портом `8000`.

1. У Coolify виберіть `docker-compose.coolify.yml`. У Environment Variables задайте **обов'язково** `FLOW2API_API_KEY` та `FLOW2API_ADMIN_PASSWORD` (довгі випадкові значення, не `han1234` / `admin`). Після зміни env зробіть redeploy: контейнер читає значення під час запуску.
2. За замовчуванням CAPTCHA-метод у вбудованому шаблоні TOML — `yescaptcha`. Для генерації додайте `FLOW2API_YESCAPTCHA_API_KEY`. Якщо використовуєте іншого провайдера, його метод виберіть у системних налаштуваннях, а ключ задайте в `FLOW2API_CAPMONSTER_API_KEY`, `FLOW2API_EZCAPTCHA_API_KEY`, `FLOW2API_CAPSOLVER_API_KEY` або `FLOW2API_REMOTE_BROWSER_API_KEY`.
3. Необов'язкові env: `FLOW2API_PLUGIN_CONNECTION_TOKEN` для Chrome-розширення, `FLOW2API_PROXY_URL` і `FLOW2API_MEDIA_PROXY_URL` для глобального проксі, `FLOW2API_ALERT_WEBHOOK_URL` для Discord-сповіщень. Залиште невикористані змінні порожніми. Після запуску `GET /health` повертає `backend_running: true`; `has_active_tokens: false` очікувано, доки немає придатних акаунтів.

`Dockerfile.coolify` копіює `config/setting_example.toml` в образ як `/app/config/setting.toml`. У ньому залишилися адреси Flow, таймаути, порт `8000`, метод CAPTCHA, параметри генерації та браузерного режиму; це **не** файл для секретів і його не треба створювати на сервері. Режим `FLOW2API_SECRETS_FROM_ENV=1` заданий у Compose. API-ключ, пароль, ключі CAPTCHA, токен розширення та глобальні проксі-URL у цьому режимі не зберігаються в SQLite: старі значення в цих полях очищуються при старті. Адмінка не дозволяє змінювати env-секрети: змінюйте їх у Coolify з redeploy.

Шаблон усе ще містить історичні прикладові `api_key` і `admin_password`, але в Coolify-режимі вони **не використовуються і не записуються в БД**. Під час міграції з попереднього запуску очистка стосується активних рядків БД, а не старих резервних копій або копій WAL: збережені раніше ключі потрібно ротувати.

Не масштабуйте цей сервіс на кілька реплік з однією SQLite-базою. Резервуйте том `flow2api_data`: у ньому зберігаються акаунти Flow, їхні змінні токени та стан роботи. Не задавайте секрети як build-time env і не зберігайте їх у Git.

Цей Compose не запускає окремий браузерний keepalive або XRDP-вхід для Google-акаунтів. Для них потрібне окреме розгортання з постійними профілями браузера та дисплеєм; див. `docs/operations/browser-keepalive.md`. Наявність API-контейнера сама по собі не підтримує Google-сесії активними.
