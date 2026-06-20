# Epic 08: Scaling

> **Goal:** Plan and implement horizontal scaling strategies across all components as the platform grows from MVP to production scale.

## Scope

- FastAPI horizontal scaling (multiple replicas)
- PostgreSQL read replicas
- Independent scraper scheduling via k8s CronJobs
- MinIO multi-node expansion

## Success Criteria

- System can scale from 0-10k listings/day to 500k+ listings/day
- Each component has a documented scaling path

## Related Spec Modules

- `specs/150-SCALING.md`
- `specs/020-ARCHITECTURE.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-38 | Scale FastAPI horizontally with multiple replicas |
| STORY-39 | Use read replicas for SELECT operations |
| STORY-40 | Schedule scrapers independently via Kubernetes CronJob |
| STORY-41 | Expand MinIO across multiple disks/nodes |
