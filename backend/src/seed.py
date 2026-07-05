"""
Database seed script.

Creates sample data for development and demonstration:
- Admin user
- Organization with projects
- Queues with retry policies
- Sample jobs in various states

Run with: python -m src.seed
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from src.core.database import async_session_factory, engine, Base
from src.core.security import hash_password
from src.auth.models import User
from src.organizations import Organization, OrgMember
from src.projects import Project
from src.queues import Queue, RetryPolicy
from src.jobs import Job
from src.workers import Worker
from src.dlq import DeadLetterQueueEntry


async def seed():
    """Seed the database with sample data."""
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        # ─── Users ───────────────────────────────────────────
        admin = User(
            email="admin@example.com",
            password_hash=hash_password("Admin123!"),
            full_name="Admin User",
            role="admin",
        )
        member = User(
            email="dev@example.com",
            password_hash=hash_password("Dev12345!"),
            full_name="Developer User",
            role="member",
        )
        db.add_all([admin, member])
        await db.flush()

        # ─── Organization ───────────────────────────────────
        org = Organization(
            name="Acme Corp",
            slug="acme-corp",
            description="Demo organization for the distributed job scheduler",
        )
        db.add(org)
        await db.flush()

        # Add members
        db.add_all([
            OrgMember(organization_id=org.id, user_id=admin.id, role="owner"),
            OrgMember(organization_id=org.id, user_id=member.id, role="member"),
        ])
        await db.flush()

        # ─── Projects ───────────────────────────────────────
        project = Project(
            organization_id=org.id,
            name="Backend Services",
            slug="backend-services",
            description="Core backend processing pipelines",
        )
        db.add(project)
        await db.flush()

        # ─── Retry Policies ─────────────────────────────────
        exp_policy = RetryPolicy(
            name="Exponential Backoff",
            strategy="exponential",
            base_delay_ms=1000,
            max_delay_ms=300000,
            multiplier=2.0,
            jitter=0.2,
        )
        fixed_policy = RetryPolicy(
            name="Fixed 5s Delay",
            strategy="fixed",
            base_delay_ms=5000,
            max_delay_ms=5000,
            multiplier=1.0,
            jitter=0.1,
        )
        linear_policy = RetryPolicy(
            name="Linear Backoff",
            strategy="linear",
            base_delay_ms=2000,
            max_delay_ms=60000,
            multiplier=1.0,
            jitter=0.15,
        )
        db.add_all([exp_policy, fixed_policy, linear_policy])
        await db.flush()

        # ─── Queues ──────────────────────────────────────────
        email_queue = Queue(
            project_id=project.id,
            name="Email Notifications",
            slug="email-notifications",
            description="Transactional email delivery",
            priority=8,
            concurrency_limit=20,
            max_retries=5,
            retry_policy_id=exp_policy.id,
            rate_limit_per_second=50,
        )
        report_queue = Queue(
            project_id=project.id,
            name="Report Generation",
            slug="report-generation",
            description="PDF and CSV report generation",
            priority=5,
            concurrency_limit=5,
            max_retries=3,
            retry_policy_id=linear_policy.id,
        )
        webhook_queue = Queue(
            project_id=project.id,
            name="Webhook Delivery",
            slug="webhook-delivery",
            description="Outbound webhook event delivery",
            priority=7,
            concurrency_limit=15,
            max_retries=10,
            retry_policy_id=exp_policy.id,
            rate_limit_per_second=100,
        )
        cleanup_queue = Queue(
            project_id=project.id,
            name="Data Cleanup",
            slug="data-cleanup",
            description="Scheduled data cleanup and archival",
            priority=3,
            concurrency_limit=3,
            max_retries=2,
            retry_policy_id=fixed_policy.id,
        )
        db.add_all([email_queue, report_queue, webhook_queue, cleanup_queue])
        await db.flush()

        # ─── Sample Jobs ────────────────────────────────────
        now = datetime.now(timezone.utc)
        jobs = []

        # Queued jobs
        for i in range(15):
            jobs.append(Job(
                queue_id=email_queue.id,
                name=f"Send welcome email #{i+1}",
                type="immediate",
                status="queued",
                payload={"to": f"user{i+1}@example.com", "template": "welcome"},
                priority=5 + (i % 5),
            ))

        # Completed jobs
        for i in range(25):
            completed_at = now - timedelta(minutes=i * 2)
            jobs.append(Job(
                queue_id=email_queue.id,
                name=f"Email delivery #{i+100}",
                type="immediate",
                status="completed",
                payload={"to": f"customer{i}@example.com", "template": "invoice"},
                result={"delivered": True, "message_id": f"msg_{uuid.uuid4().hex[:8]}"},
                priority=5,
                completed_at=completed_at,
                started_at=completed_at - timedelta(seconds=2),
                claimed_at=completed_at - timedelta(seconds=3),
            ))

        # Failed jobs
        for i in range(5):
            jobs.append(Job(
                queue_id=webhook_queue.id,
                name=f"Webhook delivery #{i+1}",
                type="immediate",
                status="failed",
                payload={"url": f"https://api.example.com/hook/{i}", "event": "order.created"},
                priority=7,
                retry_count=i + 1,
                max_retries=10,
            ))

        # Scheduled jobs
        for i in range(5):
            jobs.append(Job(
                queue_id=report_queue.id,
                name=f"Monthly report #{i+1}",
                type="scheduled",
                status="scheduled",
                payload={"report_type": "monthly", "month": f"2025-0{i+1}"},
                priority=5,
                scheduled_at=now + timedelta(hours=i + 1),
            ))

        # Recurring job
        jobs.append(Job(
            queue_id=cleanup_queue.id,
            name="Nightly data cleanup",
            type="recurring",
            status="scheduled",
            payload={"tables": ["temp_sessions", "expired_tokens"], "older_than_days": 30},
            priority=3,
            cron_expression="0 2 * * *",
            scheduled_at=now + timedelta(hours=6),
        ))

        db.add_all(jobs)
        await db.commit()

    print("✅ Database seeded successfully!")
    print("   Admin login: admin@example.com / Admin123!")
    print("   Dev login:   dev@example.com / Dev12345!")


if __name__ == "__main__":
    asyncio.run(seed())
