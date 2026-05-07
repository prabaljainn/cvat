# Copyright (C) 2020-2022 Intel Corporation
# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

import os

# Inherit parent config
from cvat.settings.production import *  # pylint: disable=wildcard-import

# https://github.com/pennersr/django-allauth
ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"

# SMTP backend (configured from environment)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ["SMTP_HOST"]
EMAIL_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_HOST_USER = os.environ["SMTP_USERNAME"]
EMAIL_HOST_PASSWORD = os.environ["SMTP_PASSWORD"]
EMAIL_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() == "true"
EMAIL_TIMEOUT = 30
DEFAULT_FROM_EMAIL = os.environ["SMTP_FROM_EMAIL"]
SERVER_EMAIL = os.environ["SMTP_FROM_EMAIL"]
