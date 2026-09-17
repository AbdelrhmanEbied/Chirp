"""Shared platform library for Chirp services.

Nothing in here contains product/business logic. It holds the cross-cutting
concerns every service needs so that a new service is a thin, boring wrapper:
configuration, logging, request context, errors, HTTP app factory, database
session management, the event bus abstraction, auth primitives and metrics.
"""

__version__ = "0.1.0"
