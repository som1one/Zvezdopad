# Инструкция по замене тестового магазина YooKassa на рабочий

## Где находятся настройки

Настройки YooKassa хранятся в файле `.env` на сервере в переменных:
- `YOOKASSA_SHOP_ID` - ID магазина
- `YOOKASSA_SECRET` - Секретный ключ

## Как заменить

### 1. На сервере найдите файл `.env`

Обычно он находится в корне проекта рядом с `docker-compose.yml` или `docker-compose.hub.yml`.

### 2. Отредактируйте файл `.env`

Замените тестовые значения на рабочие:

```bash
# БЫЛО (тестовый магазин):
YOOKASSA_SHOP_ID=123456
YOOKASSA_SECRET=test_xxxxxxxxxxxxx

# ДОЛЖНО БЫТЬ (рабочий магазин):
YOOKASSA_SHOP_ID=ваш_рабочий_shop_id
YOOKASSA_SECRET=live_xxxxxxxxxxxxx
```

**Важно:**
- Тестовые ключи начинаются с `test_`
- Рабочие ключи начинаются с `live_`
- Рабочие ключи можно получить в личном кабинете YooKassa

### 3. Перезапустите backend

После изменения `.env` нужно перезапустить backend контейнер:

```bash
docker compose -f docker-compose.hub.yml restart backend
```

Или если используете обычный docker-compose:

```bash
docker compose restart backend
```

### 4. Проверьте настройки

Откройте в админке: `/api/admin/yookassa/check`

Должно вернуться:
```json
{
  "ok": true,
  "status_code": 200,
  "shop_id": "ваш_shop_id",
  "secret_mask": "live…xxxx"
}
```

Если `ok: false` - проверьте правильность ключей.

## Где получить рабочие ключи

1. Войдите в личный кабинет YooKassa: https://yookassa.ru/my
2. Перейдите в раздел "Настройки" → "API"
3. Скопируйте:
   - **Shop ID** → в `YOOKASSA_SHOP_ID`
   - **Секретный ключ** → в `YOOKASSA_SECRET`

**Внимание:** Рабочие ключи работают с реальными платежами! Убедитесь, что используете правильный магазин.

## Проверка webhook

После замены ключей убедитесь, что webhook URL в настройках YooKassa указывает на ваш сервер:

```
https://ваш-домен.ru/api/payments/webhook
```

И что включена проверка подписи в `.env`:
```
VERIFY_WEBHOOK_SIGNATURE=true
```
