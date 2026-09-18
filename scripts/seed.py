#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "libs", "chirp-common"))

from chirp_common.ids import new_ulid  # noqa: E402
from chirp_common.security import hash_password  # noqa: E402

SEED_PASSWORD = "chirp-development-password"

FIRST_NAMES = [
    "ada", "alan", "grace", "linus", "barbara", "edsger", "donald", "margaret",
    "ken", "dennis", "radia", "leslie", "tony", "niklaus", "john", "jean",
]
LAST_NAMES = [
    "lovelace", "turing", "hopper", "torvalds", "liskov", "dijkstra", "knuth",
    "hamilton", "thompson", "ritchie", "perlman", "lamport", "hoare", "wirth",
]
TOPICS = [
    "distributed systems", "postgres indexes", "kubernetes autoscaling",
    "cold starts", "cursor pagination", "event sourcing", "cache invalidation",
    "connection pools", "backpressure", "idempotency keys", "sharding",
]

SIZES = {
    "small": (200, 10, 15),
    "medium": (5_000, 12, 40),
    "large": (50_000, 15, 60),
}


@dataclass(slots=True)
class Plan:
    users: int
    posts_per_user: int
    follows_per_user: int

    @property
    def total_posts(self) -> int:
        return self.users * self.posts_per_user


def database_url(service: str) -> str:
    explicit = os.environ.get(f"{service.upper()}_DATABASE_URL")
    if explicit:
        return explicit
    user = os.environ.get("POSTGRES_USER", "chirp")
    password = os.environ.get("POSTGRES_PASSWORD", "chirp-local-password")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/chirp_{service}"


async def seed_accounts_and_profiles(plan: Plan, batch_size: int = 1_000) -> list[str]:
    shared_hash = hash_password(SEED_PASSWORD)
    auth_engine = create_async_engine(database_url("auth"), pool_pre_ping=True)
    user_engine = create_async_engine(database_url("user"), pool_pre_ping=True)

    user_ids: list[str] = []
    accounts: list[dict[str, str]] = []
    profiles: list[dict[str, object]] = []

    for index in range(plan.users):
        user_id = new_ulid()
        handle = f"{random.choice(FIRST_NAMES)}{index}"
        user_ids.append(user_id)
        accounts.append(
            {
                "id": user_id,
                "email": f"{handle}@chirp.local",
                "password_hash": shared_hash,
            }
        )
        profiles.append(
            {
                "id": user_id,
                "username": handle,
                "display_name": (
                    f"{random.choice(FIRST_NAMES).title()} "
                    f"{random.choice(LAST_NAMES).title()}"
                ),
                "bio": f"Thinking about {random.choice(TOPICS)}.",
            }
        )

    async with auth_engine.begin() as conn:
        for start in range(0, len(accounts), batch_size):
            await conn.execute(
                text(
                    "INSERT INTO accounts (id, email, password_hash, is_admin, activated_at) "
                    "VALUES (:id, :email, :password_hash, false, now()) "
                    "ON CONFLICT (email) DO NOTHING"
                ),
                accounts[start : start + batch_size],
            )
            print(f"  accounts {min(start + batch_size, len(accounts))}/{len(accounts)}")

    async with user_engine.begin() as conn:
        for start in range(0, len(profiles), batch_size):
            await conn.execute(
                text(
                    "INSERT INTO user_profiles (id, username, display_name, bio) "
                    "VALUES (:id, :username, :display_name, :bio) "
                    "ON CONFLICT (username) DO NOTHING"
                ),
                profiles[start : start + batch_size],
            )
            print(f"  profiles {min(start + batch_size, len(profiles))}/{len(profiles)}")

    await auth_engine.dispose()
    await user_engine.dispose()
    return user_ids


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Chirp with development data.")
    parser.add_argument("--size", choices=sorted(SIZES), default="small")
    parser.add_argument("--users", type=int, default=None)
    parser.add_argument("--posts-per-user", type=int, default=None)
    parser.add_argument("--follows-per-user", type=int, default=None)
    parser.add_argument("--seed", type=int, default=1234, help="RNG seed, for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)
    users, posts, follows = SIZES[args.size]
    plan = Plan(
        users=args.users or users,
        posts_per_user=args.posts_per_user if args.posts_per_user is not None else posts,
        follows_per_user=(
            args.follows_per_user if args.follows_per_user is not None else follows
        ),
    )

    print(f"seeding {plan.users} users (~{plan.total_posts} posts planned)")
    user_ids = await seed_accounts_and_profiles(plan)
    print(f"done: {len(user_ids)} users")
    print(f"log in as any of them with the password: {SEED_PASSWORD}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
