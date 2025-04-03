import enum

from sqlalchemy import event
from sqlalchemy.ext.declarative import AbstractConcreteBase
import pendulum

from .db import db


@enum.unique
class BaseEnum(enum.Enum):
    """
    Base enum class used by all of our custom enum.Enum objects
    """
    @classmethod
    def values(cls):
        """Helper method to get the possible values for this enum"""
        return [p.value for p in list(cls)]


class BaseModel(AbstractConcreteBase):
    """
    Base model class all of our models should inhert from

    This base model ensures that all of our models have a `created_at`, and `updated_at` columns
    and that `updated_at` will automatically get updated whenever a models gets updated
    """
    SAVE_TO_AUDIT_LOG = True

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=pendulum.now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=pendulum.now)

    def __init__(self, created_at=None, updated_at=None, *args, **kwargs):
        """Common constructor to ensure we are setting `created_at` and `updated_at` properly"""
        if created_at is None:
            created_at = pendulum.now()
        if updated_at is None:
            updated_at = created_at

        return super(BaseModel, self).__init__(created_at=created_at, updated_at=updated_at, *args, **kwargs)


@event.listens_for(BaseModel, 'before_update', propagate=True)
def update_updated_at(mapper, connection, model):
    """Method to update models `updated_at` on any updated"""
    model.updated_at = pendulum.now()
