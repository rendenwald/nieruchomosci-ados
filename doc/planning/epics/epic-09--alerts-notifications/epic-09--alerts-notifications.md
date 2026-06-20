# Epic 09: Alerts + Notifications

> **Goal:** Allow users to create search alerts and receive notifications (email, push) when new matching properties are scraped.

## Scope

- User alert CRUD (create, read, delete)
- Redis Streams for alert processing pipeline
- Email notification via Alert Worker
- Browser push notifications
- Admin alerts for system health

## Success Criteria

- User creates alert → receives email when matching property appears
- Notification delivered within 5 minutes of property scrape
- Admin alerted on scraper errors and disk usage

## Related Spec Modules

- `specs/120-CACHING-STORAGE.md`
- `specs/080-API.md`
- `specs/130-MONITORING-ALERTS.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-42 | Save user search criteria when creating alert |
| STORY-43 | Notify user via email when matching property scraped |
| STORY-44 | Send browser push notification |
| STORY-45 | Notify admin via email + Slack on high scraper error rate |
| STORY-46 | Trigger critical alert to admin when DB disk > 80% |
