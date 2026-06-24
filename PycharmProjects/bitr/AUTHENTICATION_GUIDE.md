# Гайд: Аутентификация пользователей

## Текущее состояние

### ❌ Проблема: Нет реальной аутентификации

**Сейчас:**
- Все запросы возвращают фиктивного пользователя `dev_user@example.com`
- JWT проверка закомментирована
- Нет проверки паролей
- Нет интеграции с Bitrix24 для получения пользователей

**Код в `backend/core/security.py`:**
```python
def get_current_user(...) -> User:
    # JWT проверка закомментирована для разработки
    # ...
    
    # Возвращаем фиктивного пользователя без проверки токена
    return User(email="dev_user@example.com")
```

## Решение: Интеграция с Bitrix24

### Вариант 1: Аутентификация через Bitrix24 (рекомендуется)

#### 1. Получение пользователей из Bitrix24

Bitrix24 API позволяет получить контакты через:
- `crm.contact.list` - список контактов
- `crm.contact.get` - данные конкретного контакта
- `user.get` - данные пользователя Bitrix24 (если есть доступ)

#### 2. Создание системы аутентификации

**Шаг 1: Получение контактов из Bitrix24**

```python
# backend/bitrix/client.py

def get_contact_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Получает контакт из Bitrix24 по email"""
    try:
        url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.list"
        payload = {
            "filter": {"EMAIL": email},
            "select": ["ID", "NAME", "LAST_NAME", "EMAIL", "PHONE"]
        }
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        data = res.json()
        contacts = data.get("result", [])
        return contacts[0] if contacts else None
    except Exception as e:
        logger.error(f"Error getting contact from Bitrix24: {e}")
        return None
```

**Шаг 2: Проверка пароля (если хранится в Bitrix24)**

Bitrix24 обычно НЕ хранит пароли в открытом виде. Варианты:
- Использовать OAuth Bitrix24
- Хранить хеши паролей в локальной БД
- Использовать magic link (уже есть в коде)

**Шаг 3: Включить JWT проверку**

```python
# backend/core/security.py

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
        
        # Проверяем, что пользователь существует в Bitrix24
        from bitrix.client import get_contact_by_email
        contact = get_contact_by_email(email)
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Пользователь не найден"
            )
        
        return User(email=email)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен"
        )
```

### Вариант 2: Локальная БД с паролями

#### 1. Создать модель User

```python
# backend/models/user.py

from sqlalchemy import Column, Integer, String, Boolean
from models.payment_log import Base
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    bitrix_contact_id = Column(String, nullable=True)  # ID контакта в Bitrix24
    
    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.hashed_password)
    
    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)
```

#### 2. Создать эндпоинты для входа

```python
# backend/auth/router.py

@router.post("/login")
def login(email: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.verify_password(password):
        raise HTTPException(
            status_code=401,
            detail="Неверный email или пароль"
        )
    
    token = create_magic_token(email)
    return {"access_token": token, "token_type": "bearer"}
```

#### 3. Синхронизация с Bitrix24

При создании пользователя синхронизировать с Bitrix24:
```python
# Создать контакт в Bitrix24
# Сохранить contact_id в локальной БД
```

## Рекомендуемый подход

### Гибридный вариант:

1. **Magic Link для клиентов** (уже есть в коде)
   - Клиент запрашивает magic link по email
   - Получает ссылку с токеном
   - Переходит по ссылке и авторизуется

2. **Пароли для админов** (локальная БД)
   - Админы имеют пароли в локальной БД
   - Проверка через JWT после входа

3. **Синхронизация с Bitrix24**
   - При входе проверяем, что email есть в Bitrix24
   - Получаем данные контакта из Bitrix24
   - Используем для отображения имени и других данных

## Что нужно сделать

### 1. Включить JWT проверку

Раскомментировать код в `backend/core/security.py`:
```python
from jose import jwt, JWTError
```

### 2. Добавить получение контактов из Bitrix24

Создать функцию `get_contact_by_email()` в `backend/bitrix/client.py`

### 3. Создать эндпоинты для входа

- `/api/auth/login` - вход с email/паролем
- `/api/auth/magic-link` - запрос magic link (уже есть)
- `/api/auth/verify` - проверка токена

### 4. Обновить фронтенд

- Форма входа
- Сохранение токена
- Отправка токена в заголовках запросов

## Проверка готовности

### ✅ Что уже есть:
- Magic link система (не используется)
- JWT библиотека установлена
- Структура для аутентификации

### ❌ Что нужно добавить:
- Получение контактов из Bitrix24
- Проверка пользователей при запросах
- Эндпоинты для входа
- Хранение паролей (для админов) или использование OAuth

## Безопасность

⚠️ **Важно:**
- Никогда не храните пароли в открытом виде
- Используйте bcrypt для хеширования
- JWT токены должны иметь срок действия
- Проверяйте токены на каждом запросе
- Используйте HTTPS в продакшене

