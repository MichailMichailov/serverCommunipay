from rest_framework.exceptions import APIException

class DomainError(APIException):
    status_code = 400
    default_detail = "Domain error"
    default_code = "domain_error"
