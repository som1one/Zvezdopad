# Пошаговая инструкция по настройке системы

## 1. Настройка вебхука в Bitrix24

### Шаг 1: Создание входящего вебхука

1. Войдите в Bitrix24: https://karkas.bitrix24.ru
2. Перейдите в **Разработчикам** → **Входящий вебхук**
3. Нажмите **"Создать вебхук"** или используйте существующий

### Шаг 2: Настройка прав доступа

⚠️ **ВАЖНО:** Выберите права для вебхука:

**Обязательные права:**
- ✅ `crm` - доступ к CRM
- ✅ `crm.contact` - работа с контактами
- ✅ `crm.deal` - работа со сделками
- ✅ `crm.deal.list` - получение списка сделок
- ✅ `crm.deal.get` - получение данных сделки
- ✅ `crm.deal.update` - обновление сделок
- ✅ `crm.contact.list` - получение списка контактов
- ✅ `crm.contact.get` - получение данных контакта

**Как выбрать:**
1. В разделе "Настройка прав" нажмите **"+ выбрать"**
2. Выберите нужные права из списка
3. Сохраните

### Шаг 3: Сохранение URL вебхука

1. Скопируйте URL вебхука (например: `https://karkas.bitrix24.ru/rest/153/vqukf1eoovd3ba99/`)
2. Сохраните его - он понадобится для настройки `.env`

## 2. Настройка переменных окружения

### Шаг 1: Создайте файл `.env` в корне проекта

```bash
# Bitrix24
BITRIX_WEBHOOK_URL=https://karkas.bitrix24.ru/rest/153/vqukf1eoovd3ba99

# YooKassa
YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET=ваш_secret_key

# Frontend
FRONTEND_URL=http://localhost

# JWT (для аутентификации)
JWT_SECRET=ваш_секретный_ключ_минимум_32_символа

# Окружение
ENVIRONMENT=development
LOG_LEVEL=INFO
VERIFY_WEBHOOK_SIGNATURE=false
```

### Шаг 2: Замените значения

- `BITRIX_WEBHOOK_URL` - URL из шага 1.3
- `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET` - из личного кабинета YooKassa
- `JWT_SECRET` - сгенерируйте случайную строку (минимум 32 символа)

## 3. Включение аутентификации

### Шаг 1: Раскомментируйте JWT проверку

Откройте `backend/core/security.py` и раскомментируйте код:

```python
from jose import jwt, JWTError  # Раскомментировать
from core.config import settings  # Раскомментировать

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация"
        )
    
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        # Проверяем, что пользователь есть в Bitrix24
        from bitrix.user_client import verify_contact_exists
        if not verify_contact_exists(email):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Пользователь не найден в Bitrix24"
            )
        
        return User(email=email)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен"
        )
```

### Шаг 2: Удалите фиктивного пользователя

Удалите строку:
```python
# return User(email="dev_user@example.com")  # Удалить эту строку
```

## 4. Настройка Magic Link (для клиентов)

### Шаг 1: Проверьте эндпоинт

Эндпоинт `/api/auth/magic-link` уже есть в `backend/auth/magic_link.py`

### Шаг 2: Настройте отправку email/SMS

В функции `send_magic_link()` замените `print()` на реальную отправку:

```python
# Вместо:
print("MAGIC LINK:", link)

# Используйте:
# - Email отправку (SMTP)
# - SMS отправку
# - Или другой способ доставки
```

## 5. Проверка работы

### Шаг 1: Перезапустите контейнеры

```bash
docker-compose restart backend
docker-compose restart frontend
```

### Шаг 2: Проверьте подключение к Bitrix24

```bash
# Проверьте логи
docker-compose logs backend | grep "Bitrix24\|contact\|deal"

# Или используйте тестовый эндпоинт
curl http://localhost/api/admin/bitrix/test
```

### Шаг 3: Проверьте аутентификацию

1. Запросите magic link:
```bash
curl -X POST http://localhost/api/auth/magic-link?email=ваш_email@example.com
```

2. Используйте полученный токен:
```bash
curl -H "Authorization: Bearer ВАШ_ТОКЕН" http://localhost/api/installment/my
```

## 6. Настройка фронтенда

### Шаг 1: Обновите API клиент

Убедитесь, что токен отправляется в заголовках:

```javascript
// frontend/lib/apiClient.js
const token = localStorage.getItem('auth_token');
if (token) {
  config.headers.Authorization = `Bearer ${token}`;
}
```

### Шаг 2: Создайте страницу входа

Создайте форму входа, которая:
1. Запрашивает magic link по email
2. Сохраняет токен после перехода по ссылке
3. Отправляет токен в заголовках всех запросов

## 7. Проверка прав в Bitrix24

### Важно проверить:

1. **Права вебхука:**
   - Доступ к CRM
   - Доступ к контактам
   - Доступ к сделкам

2. **Права пользователя Bitrix24:**
   - Пользователь должен иметь доступ к CRM
   - Должен видеть сделки типа "Рассрочка"

3. **Пользовательские поля:**
   - Убедитесь, что поля `UF_TERM_MONTHS` и `UF_PAID_AMOUNT` существуют
   - Проверьте права на чтение/запись этих полей

## 8. Тестирование

### Проверьте:

1. ✅ Получение контактов из Bitrix24
2. ✅ Получение сделок из Bitrix24
3. ✅ Обновление `UF_PAID_AMOUNT` в Bitrix24
4. ✅ Аутентификация через JWT
5. ✅ Проверка пользователя в Bitrix24

## Проблемы и решения

### Проблема: "Пользователь не найден в Bitrix24"

**Решение:**
- Убедитесь, что контакт с таким email существует в Bitrix24
- Проверьте права вебхука на чтение контактов

### Проблема: "Ошибка при обновлении Bitrix24"

**Решение:**
- Проверьте права вебхука на обновление сделок
- Убедитесь, что поле `UF_PAID_AMOUNT` существует в Bitrix24

### Проблема: "Неверный токен"

**Решение:**
- Проверьте, что `JWT_SECRET` одинаковый в `.env` и коде
- Убедитесь, что токен не истек (срок действия 15 минут)

## Итоговый чеклист

- [ ] Вебхук создан в Bitrix24
- [ ] Права доступа настроены
- [ ] URL вебхука сохранен в `.env`
- [ ] JWT проверка включена
- [ ] Проверка пользователя в Bitrix24 добавлена
- [ ] Magic Link настроен
- [ ] Фронтенд обновлен для отправки токенов
- [ ] Все протестировано

