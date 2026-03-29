# TikTok Business API Application — Подготовка

## Цель
Получить доступ к TikTok Business API для чтения и ответа на комментарии к видео бренда aromara.ru.

## Портал подачи заявки
https://business-api.tiktok.com/portal

## Необходимые разрешения

| Permission | Зачем | Использование |
|-----------|-------|---------------|
| **Comment Management** | Читать комментарии к своим видео | Мониторинг, аналитика, CRM |
| **Comment Reply** | Отвечать на комментарии | Автоматизированные ответы с AI-генерацией |

## Описание приложения (для заявки)

### App Name
Aromara Content Manager

### App Description (EN)
Aromara Content Manager is a social media management tool for the aromatherapy and wellness brand aromara.ru. The application helps brand managers monitor and respond to audience engagement across social platforms (Instagram, YouTube, TikTok). We need TikTok Business API access to:

1. **Read comments** on our own TikTok videos to monitor audience questions and feedback about aromatherapy products and practices
2. **Reply to comments** to provide timely, helpful responses about essential oils, wellness practices, and product recommendations
3. **Track engagement metrics** to optimize content strategy

The app is used internally by the aromara.ru team (not a third-party SaaS). All data processing happens on our own servers. We do not redistribute or resell any TikTok data.

### Use Case Summary
- Monitor comments on brand's own TikTok videos
- Generate and publish AI-assisted replies to customer questions
- Aggregate engagement analytics alongside other platforms (Instagram, YouTube)
- All within a Telegram mini-app interface used by the brand team

### Data Handling
- Comments are stored in our database for team review
- No personal data is shared with third parties
- Replies are generated using AI but reviewed/approved by team before publishing
- Data retention: 90 days for comments, indefinite for aggregated analytics

## Технические детали для интеграции (после одобрения)

### Endpoints которые будем использовать:

1. **List Comments**
   ```
   GET /v2/comment/list/
   ?video_id={id}&fields=text,create_time,like_count,reply_count,user
   ```

2. **Reply to Comment**
   ```
   POST /v2/comment/reply/
   {video_id, comment_id, text}
   ```
   Ограничение: 150 символов, задержка ~15 мин.

3. **Comment Webhook**
   ```
   POST https://oauth.aromara.ru/webhooks/tiktok
   ```
   Для real-time уведомлений о новых комментариях.

### Архитектура интеграции:

```
TikTok Webhook → /webhooks/tiktok → _parse_tiktok_comment()
                                   → /api/mentions/ingest (MentionModel)
                                   → UI: Упоминания → AI reply → publish
```

### Файлы для доработки (после одобрения):

1. `bot/services/tiktok_publisher.py` — добавить `fetch_tiktok_comments()`, `reply_to_tiktok_comment()`
2. `bot/services/comments_poller.py` — добавить `_poll_tiktok_comments()` по аналогии с YouTube
3. `threads_oauth_callback.py` — добавить `/webhooks/tiktok` endpoint
4. `bot/services/social_oauth.py` — добавить скоупы `comment.list`, `comment.list.manage`
5. `miniapp/api/routers/mentions.py` — TikTok уже поддерживается как платформа в UI

### OAuth скоупы (обновить после одобрения):
```python
TIKTOK_DEFAULT_SCOPES = (
    "video.upload",
    "video.publish",
    "video.list",
    "comment.list",           # Read comments
    "comment.list.manage",    # Reply to comments
)
```

## Чеклист перед подачей

- [ ] Зарегистрироваться на https://business-api.tiktok.com/portal
- [ ] Создать Business App (не Developer App)
- [ ] Указать Callback URL: `https://oauth.aromara.ru/tiktok/callback`
- [ ] Заполнить описание приложения (текст выше)
- [ ] Приложить скриншоты работающего приложения (miniapp с разделом Упоминания)
- [ ] Указать Privacy Policy URL
- [ ] Указать Terms of Service URL
- [ ] Подать на review
- [ ] Ожидание: 3-10 рабочих дней
