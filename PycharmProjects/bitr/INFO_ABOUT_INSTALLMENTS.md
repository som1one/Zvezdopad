# Где посмотреть информацию о всех рассрочках

## 1. Через API (требует авторизации)

### Экспорт всех рассрочек с полными данными:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost/api/admin/deals/export
```

Этот endpoint возвращает:
- Статистику по всем рассрочкам
- Полный список всех рассрочек
- Для каждой рассрочки:
  - ID сделки
  - Email/телефон пользователя
  - Общая сумма
  - Оплаченная сумма
  - Остаток
  - Срок в месяцах
  - График платежей
  - Статус (paid/active/pending)

### Список всех рассрочек (краткий):
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost/api/admin/deals
```

### Детали конкретной рассрочки:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost/api/admin/deals/225
```

## 2. Через админ-панель в браузере

1. Войдите в систему по телефону/email
2. Откройте: `http://localhost/admin/deals`
3. Увидите список всех рассрочек
4. Кликните на любую рассрочку для деталей

## 3. Через файлы

- `emails_with_installments.txt` - список всех телефонов/email пользователей с рассрочкой
- `users_with_installments.txt` - подробная информация о каждой рассрочке (ID сделки, суммы, имена)

## 4. Через базу данных

```bash
docker-compose exec db psql -U postgres -d payment_logs -c "SELECT deal_id, email, total_amount, paid_amount, term_months FROM deals;"
```

## 5. Тестовый endpoint для проверки данных Bitrix24

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost/api/admin/bitrix/test
```

Показывает все данные из Bitrix24, включая все поля сделок и контактов.

