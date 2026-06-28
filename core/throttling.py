from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class ContactRateThrottle(AnonRateThrottle):
    scope = "contact"


class ComplaintCreateRateThrottle(UserRateThrottle):
    scope = "complaint_create"


class WriteRateThrottle(UserRateThrottle):
    scope = "write"
