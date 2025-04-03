from flask_env import MetaFlaskEnv


class Settings(metaclass=MetaFlaskEnv):
    """
    Environment variable configuration for our application

    Contained within this class are the default values to set.

    Any overrides should be provided as environment variables
    """
    # Current environment we are running in
    ENV = 'dev'

    # Database configuration
    SQLALCHEMY_DATABASE_URI = 'postgresql://'
    # DEV: This is needed for our audit log tracking to work
    SQLALCHEMY_TRACK_MODIFICATIONS = True
