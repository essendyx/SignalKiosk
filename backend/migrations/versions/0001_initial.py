"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(), primary_key=True), sa.Column("username", sa.String(64), nullable=False, unique=True), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("role", sa.String(32), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("last_login_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("contents", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("type", sa.String(32), nullable=False), sa.Column("description", sa.Text(), nullable=True), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("config_json", sa.Text(), nullable=False), sa.Column("default_duration_seconds", sa.Integer(), nullable=False), sa.Column("fallback_content_id", sa.String(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("auth_profiles", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(255), nullable=False, unique=True), sa.Column("type", sa.String(64), nullable=False), sa.Column("encrypted_config_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("presets", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(255), nullable=False, unique=True), sa.Column("description", sa.Text(), nullable=True), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("is_default", sa.Boolean(), nullable=False), sa.Column("loop_mode", sa.Boolean(), nullable=False), sa.Column("shuffle", sa.Boolean(), nullable=False), sa.Column("priority", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("schedules", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("preset_id", sa.String(), sa.ForeignKey("presets.id"), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("weekdays", sa.String(64), nullable=False), sa.Column("start_time", sa.String(8), nullable=False), sa.Column("end_time", sa.String(8), nullable=False), sa.Column("start_date", sa.String(10), nullable=True), sa.Column("end_date", sa.String(10), nullable=True), sa.Column("timezone", sa.String(64), nullable=False), sa.Column("priority", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("webhook_endpoints", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("slug", sa.String(255), nullable=False, unique=True), sa.Column("token_hash", sa.String(255), nullable=False), sa.Column("secret_hash", sa.String(255), nullable=True), sa.Column("allowed_actions", sa.Text(), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("rate_limit_config", sa.Text(), nullable=False), sa.Column("ip_allowlist", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("preset_items", sa.Column("id", sa.String(), primary_key=True), sa.Column("preset_id", sa.String(), sa.ForeignKey("presets.id", ondelete="CASCADE"), nullable=False), sa.Column("content_id", sa.String(), sa.ForeignKey("contents.id"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("duration_seconds", sa.Integer(), nullable=True), sa.Column("play_until_end", sa.Boolean(), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("transition", sa.String(64), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("playback_state", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("active_mode", sa.String(64), nullable=False), sa.Column("active_preset_id", sa.String(), nullable=True), sa.Column("active_content_id", sa.String(), nullable=True), sa.Column("active_override_id", sa.String(), nullable=True), sa.Column("started_at", sa.DateTime(), nullable=True), sa.Column("ends_at", sa.DateTime(), nullable=True), sa.Column("state_json", sa.Text(), nullable=False))
    op.create_table("override_events", sa.Column("id", sa.String(), primary_key=True), sa.Column("source_webhook_id", sa.String(), nullable=True), sa.Column("action", sa.String(64), nullable=False), sa.Column("payload_json", sa.Text(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("priority", sa.Integer(), nullable=False), sa.Column("duration_seconds", sa.Integer(), nullable=False), sa.Column("started_at", sa.DateTime(), nullable=False), sa.Column("ends_at", sa.DateTime(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("audit_logs", sa.Column("id", sa.String(), primary_key=True), sa.Column("actor_type", sa.String(64), nullable=False), sa.Column("actor_id", sa.String(), nullable=True), sa.Column("action", sa.String(128), nullable=False), sa.Column("entity_type", sa.String(128), nullable=False), sa.Column("entity_id", sa.String(), nullable=True), sa.Column("metadata_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("system_settings", sa.Column("key", sa.String(128), primary_key=True), sa.Column("value_json", sa.Text(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))


def downgrade() -> None:
    for table in ["system_settings", "audit_logs", "override_events", "playback_state", "preset_items", "webhook_endpoints", "schedules", "presets", "auth_profiles", "contents", "users"]:
        op.drop_table(table)
