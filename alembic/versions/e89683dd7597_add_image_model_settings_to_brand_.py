"""add image model settings to brand_settings

Revision ID: e89683dd7597
Revises: 3b57af6d5994
Create Date: 2026-03-17 15:28:16.514071

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e89683dd7597'
down_revision: Union[str, Sequence[str], None] = '3b57af6d5994'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('brand_settings', sa.Column('image_model_carousel', sa.String(length=100), server_default='gpt-image/1.5-text-to-image', nullable=False))
    op.add_column('brand_settings', sa.Column('image_model_img2img', sa.String(length=100), server_default='google/nano-banana-edit', nullable=False))
    op.add_column('brand_settings', sa.Column('image_model_reels', sa.String(length=100), server_default='gpt-image/1.5-text-to-image', nullable=False))
    op.add_column('brand_settings', sa.Column('reels_auto_images', sa.Boolean(), server_default=sa.text('0'), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('brand_settings', 'reels_auto_images')
    op.drop_column('brand_settings', 'image_model_reels')
    op.drop_column('brand_settings', 'image_model_img2img')
    op.drop_column('brand_settings', 'image_model_carousel')
